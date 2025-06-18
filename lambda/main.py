import json
import re
import os
import boto3
from botocore.exceptions import ClientError
import traceback
import uuid
import decimal # ★★★ 1. decimalライブラリをインポート ★★★

# (環境変数、boto3クライアント、DynamoDBのセットアップは変更なし)
MODEL_ID = os.environ.get("MODEL_ID", "amazon.titan-text-express-v1")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name=AWS_REGION)
TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME) if TABLE_NAME else None

# ★★★ 2. floatをDecimalに変換するヘルパー関数を追加 ★★★
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            # floatとしてシリアライズすると精度が失われる可能性があるが、
            # この関数は主にDB保存前のデータ変換に使うため、ここではfloatに変換
            return float(o)
        return super(DecimalEncoder, self).default(o)

def replace_floats_with_decimals(obj):
    if isinstance(obj, list):
        return [replace_floats_with_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: replace_floats_with_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        # 精度を保つために文字列経由でDecimalに変換
        return decimal.Decimal(str(obj))
    else:
        return obj

def handler(event, context):
    # (リクエストボディの解析、プロンプトの作成等は変更なし)
    try:
        body = json.loads(event['body'])
        lecture_text = body['lecture_text']
        # ... (中略) ...
    except Exception as e:
        return create_error_response(400, f"リクエストの解析に失敗しました: {str(e)}")

    system_prompt = f"""
# ... (プロンプトは変更なし) ...
"""
    user_prompt = f"--- 講義内容 ---\n{lecture_text}"
    request_body = {
        "schemaVersion": "messages-v1",
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {"maxTokens": 4096, "stopSequences": [], "temperature": 0.7, "topP": 0.9}
    }

    try:
        # (Bedrock呼び出し、JSON抽出ロジックは変更なし)
        # ... (中略) ...
        json_string = qa_result_text[start_index:end_index+1]
        try:
            qa_result_json = json.loads(json_string)
        except json.JSONDecodeError as e:
            if "Extra data" in str(e):
                # ... (中略) ...
                array_json_string = f"[{json_string}]"
                parsed_list = json.loads(array_json_string)
                qa_result_json = {"qa_set": parsed_list}
            else:
                raise e
        
        # DynamoDBへの保存処理
        if table:
            try:
                qa_set_id = str(uuid.uuid4())
                item_to_save = { 
                    'qa_set_id': qa_set_id, 
                    'qa_data': qa_result_json, 
                    'lecture_text_head': lecture_text[:200], 
                    'created_at': context.aws_request_id 
                }
                
                # ★★★ 3. 保存前にfloatをDecimalに変換する処理を呼び出す ★★★
                item_to_save_decimal = replace_floats_with_decimals(item_to_save)
                
                table.put_item(Item=item_to_save_decimal)
                print(f"Successfully saved QA set to DynamoDB with id: {qa_set_id}")

            except Exception as db_error:
                print(f"ERROR: Failed to save to DynamoDB. {traceback.format_exc()}")
                # DB保存エラーが発生しても、ユーザーにはQA生成成功として返す（プレビューはできるように）
                # ただし、ここでエラーメッセージを返すように変更しても良い
        
        print("Successfully generated QA.")
        return create_success_response(qa_result_json)

    except Exception as e:
        print(f"ERROR: An unexpected error occurred. {traceback.format_exc()}")
        return create_error_response(500, f"予期せぬエラーが発生しました: {str(e)}")


def create_success_response(body):
    return { 'statusCode': 200, 'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}, 'body': json.dumps(body, ensure_ascii=False, cls=DecimalEncoder) }

def create_error_response(status_code, error_message):
    return { 'statusCode': status_code, 'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}, 'body': json.dumps({"error": error_message}, ensure_ascii=False) }