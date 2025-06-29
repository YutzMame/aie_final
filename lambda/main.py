import json
import os
import boto3
import traceback
import uuid
import decimal

# --- 初期設定 ---
MODEL_ID = os.environ.get("MODEL_ID", "amazon.titan-text-express-v1")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
bedrock_runtime = boto3.client(service_name="bedrock-runtime", region_name=AWS_REGION)
TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None


# --- ヘルパー関数 ---
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o)
        return super(DecimalEncoder, self).default(o)


def replace_floats_with_decimals(obj):
    if isinstance(obj, list):
        return [replace_floats_with_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: replace_floats_with_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        return decimal.Decimal(str(obj))
    else:
        return obj


def create_success_response(body):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, ensure_ascii=False, cls=DecimalEncoder),
    }


def create_error_response(status_code, error_message):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": error_message}, ensure_ascii=False),
    }


# --- メインの処理関数 ---
def handler(event, context):
    try:
        body = json.loads(event["body"])
        lecture_text = body["lecture_text"]
        num_questions = body.get("num_questions", 5)
        difficulty = body.get("difficulty", "中")
        theme = body.get("theme", "未分類")  # テーマがなければ「未分類」に
        lecture_number = body.get("lecture_number")  # lecture_numberはオプション
    except Exception as e:
        return create_error_response(400, f"リクエストの解析に失敗しました: {str(e)}")

    system_prompt = f"""
あなたは、講義内容から学習者の理解度を測るための問題を作成する専門家です。
以下のルールに従って、与えられた講義内容から質の高いQAセットを作成してください。

# ルール
- 質問形式は「一択選択式」「記述式」をバランス良く含めること。
- {num_questions}個の問題を、難易度「{difficulty}」で作成すること。
- 回答には、なぜそれが正解なのかの短い解説を必ず含めること。
- 「記述式」問題の場合、採点に使うための最も重要な「キーワード」を3〜5個、`scoring_keywords`のリストとして必ず生成すること。
- 「記述式」問題の`correct_answer`は、要点を押さえた50字程度の簡潔な文章にすること。
- 出力は必ず指定されたJSON形式のみとし、前後に余計な文章は含めないこと。

# JSON形式の例
{{
  "qa_set": [
    {{
      "question_id": 1,
      "difficulty": "易",
      "type": "一択選択式",
      "question": "質問文1",
      "options": ["選択肢A", "選択肢B", "選択肢C", "選択肢D"],
      "correct_answer": "正解の選択肢",
      "explanation": "解説文",
      "scoring_keywords": []
    }},
    {{
      "question_id": 2,
      "difficulty": "中",
      "type": "記述式",
      "question": "質問文2",
      "options": [],
      "correct_answer": "記述式の正解文",
      "explanation": "解説文",
      "scoring_keywords": ["キーワード1", "キーワード2", "キーワード3"]
    }}
  ]
}}
"""

    user_prompt = f"--- 講義内容 ---\n{lecture_text}"
    request_body = {
        "schemaVersion": "messages-v1",
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {
            "maxTokens": 4096,
            "stopSequences": [],
            "temperature": 0.7,
            "topP": 0.9,
        },
    }

    try:
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

        start_index = qa_result_text.find("{")
        end_index = qa_result_text.rfind("}")
        if start_index == -1 or end_index == -1 or end_index < start_index:
            raise ValueError(
                "モデルの応答から有効なJSONブロックを見つけられませんでした。"
            )

        json_string = qa_result_text[start_index : end_index + 1]

        try:
            qa_result_json = json.loads(json_string)
        except json.JSONDecodeError as e:
            if "Extra data" in str(e):
                array_json_string = f"[{json_string}]"
                parsed_list = json.loads(array_json_string)
                qa_result_json = {"qa_set": parsed_list}
            else:
                raise e

        if table:
            try:
                qa_set_id = str(uuid.uuid4())
                item_to_save = {
                    "qa_set_id": qa_set_id,
                    "qa_data": qa_result_json,
                    "lecture_text_head": lecture_text[:200],
                    "created_at": context.aws_request_id,
                    "theme": theme,
                }
                # lecture_numberが指定されている場合のみ項目を追加
                if lecture_number is not None:
                    item_to_save["lecture_number"] = lecture_number

                item_to_save_decimal = replace_floats_with_decimals(item_to_save)
                table.put_item(Item=item_to_save_decimal)
                print(f"Successfully saved QA set to DynamoDB with id: {qa_set_id}")
            except Exception as e:
                print(f"ERROR: Failed to save to DynamoDB. {traceback.format_exc()}")
                return create_error_response(500, f"DBへの保存中にエラー: {str(e)}")

        return create_success_response(qa_result_json)

    except Exception as e:
        print(f"ERROR: An unexpected error occurred. {traceback.format_exc()}")
        return create_error_response(500, f"予期せぬエラーが発生しました: {str(e)}")
