import json
import os
import boto3
import traceback

# 環境変数からテーブル名を取得
TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(TABLE_NAME)

def handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    try:
        # URLのパスから削除対象のIDを取得 (例: /qas/xxxxxxxx-xxxx-xxxx)
        qa_set_id = event['pathParameters']['id']
        
        print(f"Attempting to delete item with id: {qa_set_id}")
        table.delete_item(
            Key={'qa_set_id': qa_set_id}
        )
        
        print(f"Successfully deleted item with id: {qa_set_id}")
        # 成功時はボディなし、ステータスコード204を返すのが一般的
        return {
            'statusCode': 204,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'}
        }

    except Exception as e:
        print(f"ERROR: An unexpected error occurred. {traceback.format_exc()}")
        return create_error_response(500, f"QAの削除中に予期せぬエラーが発生しました: {str(e)}")

# エラーレスポンス用のヘルパーのみ定義
def create_error_response(status_code, error_message):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({"error": error_message}, ensure_ascii=False)
    }