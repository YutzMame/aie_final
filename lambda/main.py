import json
import os
import boto3
import traceback
import uuid
import decimal

# --- 初期設定 ---
MODEL_ID = os.environ.get("MODEL_ID", "amazon.titan-text-express-v1")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name=AWS_REGION)
TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb = boto3.resource('dynamodb')
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
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(body, ensure_ascii=False, cls=DecimalEncoder)
    }

def create_error_response(status_code, error_message):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({"error": error_message}, ensure_ascii=False)
    }

# --- メインの処理関数 ---
def handler(event, context):
    try:
        body = json.loads(event['body'])
        lecture_text = body['lecture_text']
        num_questions = body.get('num_questions', 5)
        difficulty = body.get('difficulty', '中')
    except Exception as e:
        return create_error_response(400, f"リクエストの解析に失敗しました: {str(e)}")

    system_prompt = """
あなたは、講義内容から学習者の理解度を測るための問題を作成する専門家です。
# (中略... プロンプト内容は変更なし)
""".format(num_questions=num_questions, difficulty=difficulty)

    user_prompt = f"--- 講義内容 ---\n{lecture_text}"
    request_body = {
        "schemaVersion": "messages-v1",
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {"maxTokens": 4096, "stopSequences": [], "temperature": 0.7, "topP": 0.9}
    }

    try:
        response = bedrock_runtime.invoke_model(body=json.dumps(request_body), modelId=MODEL_ID)
        response_body = json.loads(response.get('body').read())
        qa_result_text = response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text')
        
        if not qa_result_text:
            raise Exception("モデルの応答からテキストを抽出できませんでした。")

        start_index = qa_result_text.find('{')
        end_index = qa_result_text.rfind('}')
        if start_index == -1 or end_index == -1 or end_index < start_index:
            raise ValueError("モデルの応答から有効なJSONブロックを見つけられませんでした。")

        json_string = qa_result_text[start_index:end_index+1]
        
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
                    'qa_set_id': qa_set_id, 
                    'qa_data': qa_result_json, 
                    'lecture_text_head': lecture_text[:200], 
                    'created_at': context.aws_request_id 
                }
                item_to_save_decimal = replace_floats_with_decimals(item_to_save)
                table.put_item(Item=item_to_save_decimal)
                print(f"Successfully saved QA set to DynamoDB with id: {qa_set_id}")
            except Exception:
                print(f"ERROR: Failed to save to DynamoDB. {traceback.format_exc()}")
        
        return create_success_response(qa_result_json)

    except Exception as e:
        print(f"ERROR: An unexpected error occurred. {traceback.format_exc()}")
        return create_error_response(500, f"予期せぬエラーが発生しました: {str(e)}")