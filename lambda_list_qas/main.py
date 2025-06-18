import json
import os
import boto3
from decimal import Decimal
import traceback

TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super(DecimalEncoder, self).default(obj)


def handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    try:
        # ★★★ 修正点2: ConsistentRead=True を追加 ★★★
        response = table.scan(ConsistentRead=True)

        items = response.get("Items", [])
        print(f"Found {len(items)} items with strong consistency.")
        return create_success_response(items)

    except Exception as e:
        print(f"ERROR: An unexpected error occurred. {traceback.format_exc()}")
        return create_error_response(
            500, f"QA一覧の取得中に予期せぬエラーが発生しました: {str(e)}"
        )


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
