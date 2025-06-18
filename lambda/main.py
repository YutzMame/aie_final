import json
import re
import os
import boto3
from botocore.exceptions import ClientError
import traceback
import uuid

# (環境変数、boto3クライアント、DynamoDBのセットアップは変更なし)
MODEL_ID = os.environ.get("MODEL_ID", "amazon.titan-text-express-v1")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name=AWS_REGION)
TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

def handler(event, context):
    # (リクエストボディの解析、プロンプトの作成等は変更なし)
    try:
        body = json.loads(event['body'])
        lecture_text = body['lecture_text']
        num_questions = body.get('num_questions', 5)
        difficulty = body.get('difficulty', '中')
    except Exception as e:
        return create_error_response(400, f"リクエストの解析に失敗しました: {str(e)}")

    system_prompt = f"""
あなたは、講義内容から学習者の理解度を測るための問題を作成する専門家です。
以下のルールに従って、与えられた講義内容から質の高いQAセットを作成してください。
# ルール
- 質問形式は「一択選択式」「記述式」をバランス良く含めること。
- {num_questions}個の問題を、難易度「{difficulty}」で作成すること。
- 回答には、なぜそれが正解なのかの短い解説を必ず含めること。
- 出力は必ず指定されたJSON形式のみとし、前後に余計な文章は含めないこと。
# JSON形式
{{ "qa_set": [ {{ "question_id": 1, ... }} ] }}
"""
    user_prompt = f"--- 講義内容 ---\n{lecture_text}"
    request_body = {
        "schemaVersion": "messages-v1",
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {"maxTokens": 4096, "stopSequences": [], "temperature": 0.7, "topP": 0.9}
    }

    try:
        # (Bedrock呼び出し、レスポンスボディの読み取りは変更なし)
        response = bedrock_runtime.invoke_model(body=json.dumps(request_body), modelId=MODEL_ID)
        response_body = json.loads(response.get('body').read())
        qa_result_text = response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text')
        
        if not qa_result_text:
            raise Exception("モデルの応答からテキストを抽出できませんでした。")

        # JSONブロックの開始と終了を探す
        start_index = qa_result_text.find('{')
        end_index = qa_result_text.rfind('}')
        
        if start_index == -1 or end_index == -1 or end_index < start_index:
            raise ValueError("モデルの応答から有効なJSONブロックを見つけられませんでした。")

        json_string = qa_result_text[start_index:end_index+1]
        
        # ★★★ ここが最終仕上げの修正点です ★★★
        try:
            # まずはそのままパースを試みる
            qa_result_json = json.loads(json_string)
        except json.JSONDecodeError as e:
            # "Extra data"エラーの場合のみ、[]で囲む修正を試みる
            if "Extra data" in str(e):
                print("JSONDecodeError with 'Extra data' detected. Attempting to fix by wrapping in an array.")
                try:
                    array_json_string = f"[{json_string}]"
                    parsed_list = json.loads(array_json_string)
                    qa_result_json = {"qa_set": parsed_list}
                except Exception as inner_e:
                    raise Exception(f"Failed to parse model output even after wrapping in array. Error: {inner_e}")
            else:
                # その他のJSONエラーはそのまま例外を送出
                raise e

        # (DynamoDBへの保存処理、成功レスポンスの返却は変更なし)
        if table:
            # ...
            qa_set_id = str(uuid.uuid4())
            item_to_save = { 'qa_set_id': qa_set_id, 'qa_data': qa_result_json, 'lecture_text_head': lecture_text[:200], 'created_at': context.aws_request_id }
            table.put_item(Item=item_to_save)
            print(f"Successfully saved QA set to DynamoDB with id: {qa_set_id}")
        
        print("Successfully generated QA.")
        return create_success_response(qa_result_json)

    except Exception as e:
        print(f"ERROR: An unexpected error occurred. {traceback.format_exc()}")
        return create_error_response(500, f"予期せぬエラーが発生しました: {str(e)}")

# (ヘルパー関数は変更なし)
def create_success_response(body):
    return { 'statusCode': 200, 'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}, 'body': json.dumps(body, ensure_ascii=False) }

def create_error_response(status_code, error_message):
    return { 'statusCode': status_code, 'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}, 'body': json.dumps({"error": error_message}, ensure_ascii=False) }