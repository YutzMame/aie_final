# lambda_handle_textract_result/main.py の全コード
import json
import os
import boto3
import re
import traceback
import uuid
from datetime import datetime

# --- AWSクライアントの初期化 ---
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-lite-v1:0")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("TABLE_NAME")

bedrock_runtime = boto3.client(service_name="bedrock-runtime", region_name=AWS_REGION)
textract_client = boto3.client("textract")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def get_textract_results(job_id):
    """Textractジョブの結果をページネーションを考慮して全て取得する"""
    full_text = ""
    pages = []

    response = textract_client.get_document_text_detection(JobId=job_id)
    pages.append(response)

    next_token = response.get("NextToken")
    while next_token:
        response = textract_client.get_document_text_detection(
            JobId=job_id, NextToken=next_token
        )
        pages.append(response)
        next_token = response.get("NextToken")

    for page in pages:
        for item in page["Blocks"]:
            if item["BlockType"] == "LINE":
                full_text += item["Text"] + "\n"

    return full_text


def generate_qa_from_text(lecture_text, num_questions, difficulty):
    # この関数は generate-from-text のものと全く同じでOK
    print(
        f"Generating {num_questions} QAs with difficulty '{difficulty}' from extracted text."
    )
    system_prompt = f"""
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
      "question": "質問文",
      "options": ["選択肢A", "選択肢B", "選択肢C", "選択肢D"],
      "correct_answer": "正解の選択肢",
      "explanation": "解説文"
    }}
  ]
}}
"""
    user_prompt = f"--- 講義内容 ---\n{lecture_text}"
    request_body = {
        "schemaVersion": "messages-v1",
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {"maxTokens": 4096, "temperature": 0.7, "topP": 0.9},
    }
    response = bedrock_runtime.invoke_model(
        body=json.dumps(request_body), modelId=MODEL_ID
    )
    response_body = json.loads(response.get("body").read())
    qa_result_text = (
        response_body.get("output", {})
        .get("message", {})
        .get("content", [{}])[0]
        .get("text")
    )

    if not qa_result_text:
        raise Exception("モデルの応答からテキストを抽出できませんでした。")

    json_match = re.search(r"\{.*\}", qa_result_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))
    else:
        raise Exception("モデルの応答から有効なJSONを抽出できませんでした。")


def handler(event, context):
    print(f"Received SNS event: {json.dumps(event)}")

    # SNSメッセージからTextractのジョブ情報を取得
    message = json.loads(event["Records"][0]["Sns"]["Message"])
    job_id = message["JobId"]
    status = message["Status"]
    s3_object_info = message["DocumentLocation"]["S3Object"]
    bucket = s3_object_info["Bucket"]
    key = s3_object_info["Name"]

    if status != "SUCCEEDED":
        print(f"Textract job failed for s3://{bucket}/{key} with status: {status}")
        return

    try:
        # Textractから文字抽出結果を取得
        extracted_text = get_textract_results(job_id)
        if not extracted_text.strip():
            raise ValueError("Textract did not return any text.")

        # S3オブジェクトのメタデータを取得（Streamlitアプリから渡された情報）
        s3_object_meta = boto3.client("s3").head_object(Bucket=bucket, Key=key)
        metadata = s3_object_meta.get("Metadata", {})
        theme = metadata.get("theme", "untitled")
        lecture_number = int(metadata.get("lecture_number", 1))
        num_questions = int(metadata.get("num_questions", 5))
        difficulty = metadata.get("difficulty", "中")

        # BedrockでQAを生成
        qa_json = generate_qa_from_text(extracted_text, num_questions, difficulty)

        # DynamoDBに保存
        qa_set_id = str(uuid.uuid4())
        item_to_save = {
            "qa_set_id": qa_set_id,
            "qa_data": qa_json,
            "theme": theme,
            "lecture_number": lecture_number,
            "source_file": key,
            "created_at": datetime.utcnow().isoformat(),
        }
        table.put_item(Item=item_to_save)

        print(f"Successfully processed and saved QA for s3://{bucket}/{key}")
        return {"status": "success"}

    except Exception as e:
        print(f"Error processing Textract result for s3://{bucket}/{key}")
        print(traceback.format_exc())
        raise e
