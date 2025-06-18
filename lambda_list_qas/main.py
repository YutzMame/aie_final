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
            if obj % 1 == 0:
                return int(obj)
            else:
                return float(obj)
        return super(DecimalEncoder, self).default(obj)


def handler(event, context):
    print(f"Received event: {json.dumps(event)}")

    # クエリパラメータを取得
    params = event.get("queryStringParameters")

    try:

        if params and "theme" in params:
            theme = params["theme"]
            print(f"Querying for theme: {theme}")

            # 基本となる検索条件を作成
            key_condition_expression = Key("theme").eq(theme)

            # もし'lecture_number'もあれば、検索条件に追加
            if "lecture_number" in params and params["lecture_number"]:
                try:
                    lecture_num = int(params["lecture_number"])
                    key_condition_expression = key_condition_expression & Key(
                        "lecture_number"
                    ).eq(lecture_num)
                    print(f"Adding lecture_number filter: {lecture_num}")
                except (ValueError, TypeError):
                    # lecture_numberが不正な値の場合は無視する
                    print(
                        f"Invalid lecture_number parameter ignored: {params['lecture_number']}"
                    )
                    pass

            # インデックス(GSI)を使ってクエリを実行
            response = table.query(
                IndexName="ThemeLectureIndex",
                KeyConditionExpression=key_condition_expression,
            )

        else:
            # パラメータがなければ、これまで通り全件取得
            print("No theme parameter found. Scanning for all items.")

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
