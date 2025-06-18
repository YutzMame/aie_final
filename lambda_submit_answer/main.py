from decimal import Decimal
import json
import os
import boto3
import traceback
import uuid

TABLE_NAME = os.environ.get("TABLE_NAME")
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)


def default_json_serializer(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def convert_floats_to_decimal(obj):
    if isinstance(obj, list):
        return [convert_floats_to_decimal(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: convert_floats_to_decimal(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        return Decimal(str(obj))  # strを経由して精度を守る
    else:
        return obj


def handler(event, context):
    try:
        qa_set_id = event["pathParameters"]["id"]
        submission_body = json.loads(event["body"])
        user_answers = submission_body.get("answers", [])

        # DBから正解データを取得
        response = table.get_item(Key={"qa_set_id": qa_set_id})
        item = response.get("Item")
        if not item:
            return create_error_response(404, "指定されたQAセットが見つかりません。")

        correct_answers = item.get("qa_data", {}).get("qa_set", [])

        # 採点処理
        score = 0
        total = len(correct_answers)
        results = []

        for i, qa in enumerate(correct_answers):
            user_ans_data = user_answers[i]
            user_ans = user_ans_data.get("answer")
            is_flagged = user_ans_data.get("is_flagged", False)
            is_correct = False

            if is_flagged:
                is_correct = False
            elif qa.get("type") == "一択選択式":
                if user_ans == qa.get("correct_answer"):
                    is_correct = True
            elif qa.get("type") == "記述式":
                keywords = qa.get("scoring_keywords", [])
                if keywords and user_ans:
                    # 全てのキーワードが回答に含まれていれば正解とする
                    is_correct = all(
                        keyword.lower() in user_ans.lower() for keyword in keywords
                    )

            if is_correct:
                score += 1

            results.append(
                {
                    "question_id": qa.get("question_id"),
                    "is_correct": is_correct,
                    "is_flagged": is_flagged,
                }
            )

        # 採点結果を作成
        score_data = {
            "submission_id": str(uuid.uuid4()),
            "score": (score / total) * 100 if total > 0 else 0,
            "correct_count": score,
            "total_count": total,
            "results": results,
            "submitted_at": context.aws_request_id,
        }

        # DBに採点結果を追記
        score_data_decimal = convert_floats_to_decimal(score_data)
        table.update_item(
            Key={"qa_set_id": qa_set_id},
            UpdateExpression="SET submissions = list_append(if_not_exists(submissions, :empty_list), :s)",
            ExpressionAttributeValues={":s": [score_data_decimal], ":empty_list": []},
        )

        return create_success_response(score_data)

    except Exception as e:
        print(f"ERROR: {traceback.format_exc()}")
        return create_error_response(
            500, f"回答の処理中にエラーが発生しました: {str(e)}"
        )


def create_success_response(body):
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body, default=default_json_serializer),
    }


def create_error_response(status_code, error_message):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps({"error": error_message}),
    }
