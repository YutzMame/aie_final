import aws_cdk as core
import aws_cdk.assertions as assertions

from qa_system.aie_final_stack import AieFinalStack

# example tests. To run these tests, uncomment this file along with the example
# resource in aie_final/aie_final_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = AieFinalStack(app, "aie-final")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
