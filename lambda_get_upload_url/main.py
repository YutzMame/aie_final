# lambda_get_upload_url/main.py

import json
import os
import boto3
from botocore.exceptions import ClientError
import uuid

s3_client = boto3.client("s3")
BUCKET_NAME = os.environ.get("UPLOAD_BUCKET_NAME")


def handler(event, context):
    try:
        # フロントエンドからリクエストボディを受け取る
        body = json.loads(event["body"])
        file_name = body.get("file_name", "default.pptx")
        theme = body.get("theme", "untitled")
        lecture_number = body.get("lecture_number", "1")
        num_questions = body.get("num_questions", "5")
        difficulty = body.get("difficulty", "中")

        # S3内でユニークなキーを生成
        object_key = f"uploads/{uuid.uuid4()}-{file_name}"

        # 事前署名付きPOSTを生成
        presigned_post = s3_client.generate_presigned_post(
            Bucket=BUCKET_NAME,
            Key=object_key,
            Fields={
                "x-amz-meta-theme": theme,
                "x-amz-meta-lecture_number": str(lecture_number),
                "x-amz-meta-num_questions": str(num_questions),
                "x-amz-meta-difficulty": difficulty,
            },
            Conditions=[
                {"x-amz-meta-theme": theme},
                {"x-amz-meta-lecture_number": str(lecture_number)},
                {"x-amz-meta-num_questions": str(num_questions)},
                {"x-amz-meta-difficulty": difficulty},
            ],
            ExpiresIn=3600,  # 1 hour
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            # フロントエンドが必要とするURLとフォームフィールドを返す
            "body": json.dumps(presigned_post),
        }

    except ClientError as e:
        print(f"ERROR: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
    except Exception as e:
        print(f"ERROR: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
