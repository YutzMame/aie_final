# qa_system/qa_system_stack.py
from aws_cdk import (
    Stack, aws_lambda as _lambda, aws_apigateway as apigw,
    Duration, CfnOutput, aws_iam
)
from constructs import Construct

class QaSystemStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        qa_lambda = _lambda.Function(self, "QaGeneratorFunction",
            runtime=_lambda.Runtime.PYTHON_3_11,
            code=_lambda.Code.from_asset("lambda"),
            handler="main.handler",
            timeout=Duration.seconds(30)
            environment={
                "MODEL_ID": "amazon.nova-lite-v1:0" 
            }
        )

        qa_lambda.add_to_role_policy(
            aws_iam.PolicyStatement(
                effect=aws_iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel"],
                resources=["*"]
            )
        )

        api = apigw.LambdaRestApi(self, "QaApiEndpoint",
            handler=qa_lambda,
            proxy=False,
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS
            )
        )

        generate_resource = api.root.add_resource("generate")
        generate_resource.add_method("POST")

        CfnOutput(self, "ApiUrl", value=api.url)