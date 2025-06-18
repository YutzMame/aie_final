# qa_system/qa_system_stack.py
from aws_cdk import aws_dynamodb as dynamodb
from datetime import datetime
from aws_cdk import (
    Stack, aws_lambda as _lambda, aws_apigateway as apigw,
    Duration, CfnOutput, aws_iam,
    aws_dynamodb as dynamodb,
    RemovalPolicy
)
from constructs import Construct

class QaSystemStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        qa_table = dynamodb.Table(self, "QaTable",
            partition_key=dynamodb.Attribute(
                name="qa_set_id",
                type=dynamodb.AttributeType.STRING
            ),
            removal_policy=RemovalPolicy.DESTROY, 
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST
        )

        qa_lambda = _lambda.Function(self, "QaGeneratorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda"),
            handler="main.handler",
            timeout=Duration.minutes(2),
            description=f"Generates QA - deployed on {datetime.now()}",
            environment={
                "MODEL_ID": "us.amazon.nova-lite-v1:0" 
            }
        )
   
        qa_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(
                effect=aws_iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=["*"]
            )
        )
        qa_table.grant_read_write_data(qa_lambda)

        # QA一覧取得Lambda
        list_qas_lambda = _lambda.Function(self, "ListQasFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_list_qas"),
            handler="main.handler",
            timeout=Duration.seconds(30),
            description=f"Lists QAs - deployed on {datetime.now()}",
            environment={"TABLE_NAME": qa_table.table_name}
        )
        qa_table.grant_read_data(list_qas_lambda) # 読み取り権限を付与

        # QA削除Lambda
        delete_qa_lambda = _lambda.Function(self, "DeleteQaFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda_delete_qa"),
            handler="main.handler",
            timeout=Duration.seconds(30),
            description=f"Deletes a QA - deployed on {datetime.now()}",
            environment={"TABLE_NAME": qa_table.table_name}
        )
        qa_table.grant_write_data(delete_qa_lambda) # 書き込み(削除)権限を付与

        # API Gatewayの設定
        api = apigw.RestApi(self, "QaApiEndpoint", # ★★★ 6. 構成を少し変更 ★★★
            rest_api_name="QA System Service",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key"]
            )
        )

        generate_resource = api.root.add_resource("generate")
        generate_resource.add_method("POST", apigw.LambdaIntegration(qa_lambda))

        # GET /qas
        qas_resource = api.root.add_resource("qas")
        qas_resource.add_method("GET", apigw.LambdaIntegration(list_qas_lambda))

        # DELETE /qas/{id}
        qa_item_resource = qas_resource.add_resource("{id}")
        qa_item_resource.add_method("DELETE", apigw.LambdaIntegration(delete_qa_lambda))

        CfnOutput(self, "ApiUrl", value=api.url)