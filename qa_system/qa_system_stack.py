from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    Duration,
    CfnOutput,
    aws_iam,
    aws_dynamodb as dynamodb,
    RemovalPolicy,
)
from constructs import Construct


class QaSystemStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        qa_table = dynamodb.Table(
            self,
            "QaTable",
            partition_key=dynamodb.Attribute(
                name="qa_set_id", type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY,
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

        # テーマと講義回数で検索するためのインデックス(GSI)を追加
        qa_table.add_global_secondary_index(
            index_name="ThemeLectureIndex",
            partition_key=dynamodb.Attribute(
                name="theme", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="lecture_number", type=dynamodb.AttributeType.NUMBER
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        qa_lambda = _lambda.Function(
            self,
            "QaGeneratorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda"),
            handler="main.handler",
            description="Generates QA",
            timeout=Duration.minutes(3),
            environment={
                "MODEL_ID": "amazon.nova-lite-v1:0",
                "TABLE_NAME": qa_table.table_name,
            },
        )

        qa_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(actions=["bedrock:InvokeModel", "bedrock:Converse"], resources=["*"])
        )
        qa_table.grant_read_write_data(qa_lambda)

        list_qas_lambda = _lambda.Function(
            self,
            "ListQasFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_list_qas"),
            handler="main.handler",
            timeout=Duration.seconds(30),
            environment={"TABLE_NAME": qa_table.table_name},
        )
        qa_table.grant_read_data(list_qas_lambda)
        qa_table.grant_read_data_on_index(list_qas_lambda, "ThemeLectureIndex")

        delete_qa_lambda = _lambda.Function(
            self,
            "DeleteQaFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_delete_qa"),
            handler="main.handler",
            timeout=Duration.seconds(30),
            environment={"TABLE_NAME": qa_table.table_name},
        )
        qa_table.grant_write_data(delete_qa_lambda)

        # API Gatewayを定義
        api = apigw.RestApi(
            self,
            "QaApiEndpoint",
            rest_api_name="QA System Service",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=[
                    "Content-Type",
                    "X-Amz-Date",
                    "Authorization",
                    "X-Api-Key",
                ],
            ),
        )

        # 全てのエンドポイントに `authorization_type=apigw.AuthorizationType.NONE` を追加

        # 1. QA生成エンドポイント
        generate_resource = api.root.add_resource("generate")
        generate_resource.add_method(
            "POST",
            apigw.LambdaIntegration(qa_lambda),
            authorization_type=apigw.AuthorizationType.NONE,
        )

        # 2. QA一覧取得エンドポイント
        qas_resource = api.root.add_resource("qas")
        qas_resource.add_method(
            "GET",
            apigw.LambdaIntegration(list_qas_lambda),
            authorization_type=apigw.AuthorizationType.NONE,
        )

        # 3. QA削除エンドポイント
        qa_item_resource = qas_resource.add_resource("{id}")
        qa_item_resource.add_method(
            "DELETE",
            apigw.LambdaIntegration(delete_qa_lambda),
            authorization_type=apigw.AuthorizationType.NONE,
        )

        # 5. 回答を処理するLambdaを定義
        submit_answer_lambda = _lambda.Function(self, "SubmitAnswerFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_submit_answer"), # <-- 新しいフォルダ名
            handler="main.handler",
            timeout=Duration.seconds(30),
            environment={"TABLE_NAME": qa_table.table_name}
        )
        # テーブルへの読み書き権限を付与
        qa_table.grant_read_write_data(submit_answer_lambda)

        # 6. 新しいAPIエンドポイントを追加
        # /qas/{id}/submit
        submit_resource = qa_item_resource.add_resource("submit")
        submit_resource.add_method(
            "POST",
            apigw.LambdaIntegration(submit_answer_lambda),
            authorization_type=apigw.AuthorizationType.NONE
        )

        CfnOutput(self, "ApiUrl", value=api.url)
