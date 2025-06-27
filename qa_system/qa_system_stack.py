import os
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
from datetime import datetime


class QaSystemStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ----------------------------------------------------------------
        # DynamoDB Table
        # ----------------------------------------------------------------
        qa_table = dynamodb.Table(
            self,
            "QaTable",
            partition_key=dynamodb.Attribute(
                name="qa_set_id", type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY,
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
        )

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

        # ----------------------------------------------------------------
        # Lambda Layer for python-pptx
        # ----------------------------------------------------------------

        pptx_layer_arn = (
            "arn:aws:lambda:us-east-1:922058108332:layer:python-pptx-layer:1"
        )
        pptx_layer = _lambda.LayerVersion.from_layer_version_arn(
            self, "PptxLayer", layer_version_arn=pptx_layer_arn
        )

        # ----------------------------------------------------------------
        # Lambda Functions
        # ----------------------------------------------------------------

        # 1. テキストからのQA生成Lambda
        qa_lambda = _lambda.Function(
            self,
            "QaGeneratorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda"),
            handler="main.handler",
            description=f"Generates QA from text - {datetime.now()}",
            timeout=Duration.minutes(3),
            environment={
                "MODEL_ID": "us.amazon.nova-lite-v1:0",
                "TABLE_NAME": qa_table.table_name,
            },
        )
        qa_table.grant_read_write_data(qa_lambda)
        qa_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"])
        )

        # 2. PPTXからのQA生成Lambda (★新規追加★)
        ppt_processor_lambda = _lambda.Function(
            self,
            "PptProcessorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_ppt_processor"),
            handler="main.handler",
            timeout=Duration.minutes(5),  # ファイル処理があるので長めに
            memory_size=512,  # メモリも多めに
            layers=[pptx_layer],  # レイヤーを関連付け
            description=f"Processes PPTX and generates QA - {datetime.now()}",
            environment={
                "MODEL_ID": "us.amazon.nova-lite-v1:0",
                "TABLE_NAME": qa_table.table_name,
            },
        )
        qa_table.grant_read_write_data(ppt_processor_lambda)
        ppt_processor_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"])
        )

        # 3. QA一覧取得Lambda
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

        # 4. QA削除Lambda
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

        # 5. 回答提出Lambda
        submit_answer_lambda = _lambda.Function(
            self,
            "SubmitAnswerFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_submit_answer"),
            handler="main.handler",
            timeout=Duration.seconds(30),
            environment={"TABLE_NAME": qa_table.table_name},
        )
        qa_table.grant_read_write_data(submit_answer_lambda)

        # ----------------------------------------------------------------
        # API Gateway
        # ----------------------------------------------------------------
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
            # ★★★ PPTXファイル(バイナリ)を受け付けるための設定を追加 ★★★
            binary_media_types=[
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ],
        )

        # --- エンドポイントの定義 ---

        # テキストから生成
        generate_resource = api.root.add_resource("generate-from-text")
        generate_resource.add_method("POST", apigw.LambdaIntegration(qa_lambda))

        # PPTXから生成 (★新規追加★)
        ppt_generate_resource = api.root.add_resource("generate-from-ppt")
        ppt_generate_resource.add_method(
            "POST", apigw.LambdaIntegration(ppt_processor_lambda)
        )

        # QA一覧と個別操作
        qas_resource = api.root.add_resource("qas")
        qas_resource.add_method("GET", apigw.LambdaIntegration(list_qas_lambda))

        qa_item_resource = qas_resource.add_resource("{id}")
        qa_item_resource.add_method("DELETE", apigw.LambdaIntegration(delete_qa_lambda))

        # 回答提出
        submit_resource = qa_item_resource.add_resource("submit")
        submit_resource.add_method(
            "POST", apigw.LambdaIntegration(submit_answer_lambda)
        )

        # ----------------------------------------------------------------
        # Outputs
        # ----------------------------------------------------------------
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "TableName", value=qa_table.table_name)
