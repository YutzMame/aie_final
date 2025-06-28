import os
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_lambda_event_sources as lambda_event_sources,
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
        # S3 Bucket for PPTX Uploads
        # ----------------------------------------------------------------
        upload_bucket = s3.Bucket(
            self,
            "PptxUploadBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[
                        s3.HttpMethods.PUT,
                        s3.HttpMethods.POST,
                        s3.HttpMethods.GET,
                        s3.HttpMethods.HEAD,
                    ],
                    allowed_origins=["*"],  # 本番ではStreamlitのドメインに限定
                    allowed_headers=["*"],
                    max_age=3000,
                )
            ],
        )

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
            "arn:aws:lambda:us-east-1:922058108332:layer:python-pptx-layer2:1"
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
            architecture=_lambda.Architecture.ARM_64,
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

        # 2. PPTX処理用Lambda
        ppt_processor_lambda = _lambda.Function(
            self,
            "PptProcessorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_ppt_processor"),
            handler="main.handler",
            timeout=Duration.minutes(5),
            memory_size=512,
            layers=[pptx_layer],
            description=f"Processes PPTX from S3 - deployed on {datetime.now()}",
            environment={
                "MODEL_ID": "us.amazon.nova-lite-v1:0",
                "TABLE_NAME": qa_table.table_name,
            },
        )
        # S3バケットからの読み取り権限と、DynamoDBへの書き込み権限を付与
        upload_bucket.grant_read(ppt_processor_lambda)
        qa_table.grant_read_write_data(ppt_processor_lambda)
        ppt_processor_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"])
        )
        ppt_processor_lambda.add_event_source(
            lambda_event_sources.S3EventSource(
                upload_bucket,
                events=[s3.EventType.OBJECT_CREATED],
                filters=[s3.NotificationKeyFilter(prefix="uploads/", suffix=".pptx")],
            )
        )

        # 3. 事前署名付きURL生成Lambda
        get_upload_url_lambda = _lambda.Function(
            self,
            "GetUploadUrlFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_get_upload_url"),
            handler="main.handler",
            timeout=Duration.seconds(30),
            environment={"UPLOAD_BUCKET_NAME": upload_bucket.bucket_name},
        )
        # S3バケットへの書き込みを許可する権限を付与
        upload_bucket.grant_put(get_upload_url_lambda)
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
            binary_media_types=[
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ],
        )

        # --- エンドポイントの定義 ---

        # テキストから生成
        generate_resource = api.root.add_resource("generate-from-text")
        generate_resource.add_method("POST", apigw.LambdaIntegration(qa_lambda))

        # PPTXから生成
        get_upload_url_resource = api.root.add_resource("get-upload-url")
        get_upload_url_resource.add_method(
            "POST", apigw.LambdaIntegration(get_upload_url_lambda)
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
        CfnOutput(self, "UploadBucketName", value=qa_table.table_name)
