# lambda_ppt_processor/main.py (完成版)

import json
import os
import boto3
import base64
import io
import re
import traceback
from pptx import Presentation

# Bedrockクライアントの初期化
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-lite-v1:0")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
bedrock_runtime = boto3.client(service_name="bedrock-runtime", region_name=AWS_REGION)


def generate_qa_from_text(lecture_text, num_questions, difficulty):
    """
    抽出されたテキストを元に、Bedrockを呼び出してQAを生成する関数。
    """
    print(
        f"Generating {num_questions} QAs with difficulty '{difficulty}' from extracted text."
    )

    prompt = f"""
あなたは、講義内容から学習者の理解度を測るための問題を作成する専門家です。
以下のルールに従って、与えられた講義内容から質の高いQAセットを作成してください。

# ルール
- 質問形式は「一択選択式」「記述式」をバランス良く含めること。
- {num_questions}個の問題を、難易度「{difficulty}」で作成すること。
- 回答には、なぜそれが正解なのかの短い解説を必ず含めること。
- 出力は必ず指定されたJSON形式のみとし、前後に余計な文章は含めないこと。

# JSON形式
{{
  "qa_set": [
    {{
      "question_id": 1,
      "difficulty": "易",
      "type": "一択選択式",
      "question_text": "質問文",
      "options": ["選択肢A", "選択肢B", "選択肢C", "選択肢D"],
      "answer": "正解の選択肢",
      "explanation": "解説文"
    }}
  ]
}}

---
講義内容:
{lecture_text}
"""

    # Nova/Titanモデルが期待する正しいリクエストボディ
    # ★★★ この部分が以前完成させたロジック ★★★
    request_body = {
        "inputText": prompt,
        "textGenerationConfig": {
            "maxTokenCount": 4096,
            "stopSequences": [],
            "temperature": 0.7,
            "topP": 0.9,
        },
    }

    print(f"Calling Bedrock with payload...")
    response = bedrock_runtime.invoke_model(
        body=json.dumps(request_body), modelId=MODEL_ID
    )

    response_body = json.loads(response.get("body").read())
    qa_result_text = response_body.get("results")[0].get("outputText")

    json_match = re.search(r"\{.*\}", qa_result_text, re.DOTALL)
    if json_match:
        qa_result_json = json.loads(json_match.group(0))
        return qa_result_json
    else:
        raise Exception("モデルの応答から有効なJSONを抽出できませんでした。")


def handler(event, context):
    try:
        print("Received request to generate QA from PPTX file.")
        # API GatewayからBase64エンコードされたファイルデータを受け取る
        body = json.loads(event["body"])
        file_content_base64 = body["file_content"]

        # リクエストから設定値を受け取る（なければデフォルト値）
        num_questions = body.get("num_questions", 5)
        difficulty = body.get("difficulty", "中")

        # デコードしてバイナリデータに戻す
        decoded_file = base64.b64decode(file_content_base64)

        # メモリ上でファイルを扱う
        ppt_stream = io.BytesIO(decoded_file)
        presentation = Presentation(ppt_stream)

        # 全スライドからテキストを抽出
        extracted_text = []
        for slide in presentation.slides:
            for shape in slide.shapes:
                if hasattr(shape, "text"):
                    extracted_text.append(shape.text)

        lecture_text = "\n".join(extracted_text)
        print(f"Extracted {len(lecture_text)} characters from PPTX.")

        # 抽出したテキストを使ってQAを生成（上記の関数を呼び出す）
        qa_json = generate_qa_from_text(lecture_text, num_questions, difficulty)

        print("Successfully generated and processed QA from PPTX.")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "body": json.dumps(qa_json),
        }
    except Exception as e:
        print(f"ERROR: {traceback.format_exc()}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
