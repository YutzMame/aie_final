import os
from aws_cdk import (
    Stack,
    aws_lambda as _lambda,
    aws_apigateway as apigw,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_lambda_event_sources as lambda_event_sources,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
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
        # S3 Bucket for PDF Uploads
        # ----------------------------------------------------------------
        upload_bucket = s3.Bucket(
            self,
            "PdfUploadBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            cors=[
                s3.CorsRule(
                    allowed_methods=[
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
        # Lambda Functions
        # ----------------------------------------------------------------

        # 1. テキストからのQA生成Lambda
        # --- SNS Topic for Textract Notifications ---
        textract_sns_topic = sns.Topic(self, "TextractCompletionTopic")

        # --- IAM Role for Textract to publish to SNS ---
        textract_role = aws_iam.Role(
            self,
            "TextractSnsRole",
            assumed_by=aws_iam.ServicePrincipal("textract.amazonaws.com"),
        )
        textract_sns_topic.grant_publish(textract_role)

        # --- New Lambda Functions for PDF Processing ---

        # 1. Start PDF Processing Lambda (S3 Trigger)
        start_pdf_lambda = _lambda.Function(
            self,
            "StartPdfProcessingFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            architecture=_lambda.Architecture.ARM_64,
            code=_lambda.Code.from_asset("lambda_start_pdf_processing"),
            handler="main.handler",
            timeout=Duration.seconds(60),
            environment={
                "SNS_TOPIC_ARN": textract_sns_topic.topic_arn,
                "TEXTRACT_ROLE_ARN": textract_role.role_arn,
            },
        )
        start_pdf_lambda.add_event_source(
            lambda_event_sources.S3EventSource(
                upload_bucket,
                events=[s3.EventType.OBJECT_CREATED],
                filters=[s3.NotificationKeyFilter(prefix="uploads/", suffix=".pdf")],
            )
        )
        start_pdf_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=["textract:StartDocumentTextDetection"],
                resources=["*"],
            )
        )
        start_pdf_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[textract_role.role_arn],
            )
        )

        # 2. Handle Textract Result Lambda (SNS Trigger)
        handle_textract_lambda = _lambda.Function(
            self,
            "HandleTextractResultFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            architecture=_lambda.Architecture.ARM_64,
            code=_lambda.Code.from_asset("lambda_handle_textract_result"),
            handler="main.handler",
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
                "MODEL_ID": "us.amazon.nova-lite-v1:0",
                "TABLE_NAME": qa_table.table_name,
            },
        )
        handle_textract_lambda.add_event_source(
            lambda_event_sources.SnsEventSource(textract_sns_topic)
        )
        handle_textract_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"])
        )
        handle_textract_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(
                actions=["textract:GetDocumentTextDetection"], resources=["*"]
            )
        )
        qa_table.grant_read_write_data(handle_textract_lambda)
        upload_bucket.grant_read(handle_textract_lambda)

        # 3. 事前署名付きURL生成Lambda
        get_upload_url_lambda = _lambda.Function(
            self,
            "GetUploadUrlFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            architecture=_lambda.Architecture.ARM_64,
            code=_lambda.Code.from_asset("lambda_get_upload_url"),
            handler="main.handler",
            timeout=Duration.seconds(30),
            environment={"UPLOAD_BUCKET_NAME": upload_bucket.bucket_name},
        )
        # S3バケットへの書き込みを許可する権限を付与
        upload_bucket.grant_write(get_upload_url_lambda)
        # 3. QA一覧取得Lambda
        list_qas_lambda = _lambda.Function(
            self,
            "ListQasFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            architecture=_lambda.Architecture.ARM_64,
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
            architecture=_lambda.Architecture.ARM_64,
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
            architecture=_lambda.Architecture.ARM_64,
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
        CfnOutput(self, "UploadBucketName", value=upload_bucket.bucket_name)
