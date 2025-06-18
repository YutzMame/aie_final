import aws_cdk as core

# import aws_cdk.assertions as assertions  <-- 削除
from qa_system.aie_final_stack import QaSystemStack


def test_stack_synthesis():
    app = core.App()
    # stack = AieFinalStack(app, "aie-final") <-- 削除
    QaSystemStack(
        app, "QaSystemStack-Test"
    )  # スタックがエラーなく初期化できるかだけをテスト
    pass
