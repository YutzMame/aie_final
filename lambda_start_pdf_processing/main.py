# lambda_start_pdf_processing/main.py
import os
import boto3
import urllib.parse
import json

textract_client = boto3.client("textract")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN")
TEXTRACT_ROLE_ARN = os.environ.get("TEXTRACT_ROLE_ARN")


def handler(event, context):
    print(f"Received S3 event: {json.dumps(event)}")

    # S3イベントからバケット名とオブジェクトキーを取得
    bucket = event["Records"][0]["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(
        event["Records"][0]["s3"]["object"]["key"], encoding="utf-8"
    )

    # Textractに渡すS3オブジェクトの情報を設定
    document_location = {"S3Object": {"Bucket": bucket, "Name": key}}

    # Textractの非同期処理を開始
    # 処理完了後、SNSトピックに通知を送信するように設定
    try:
        response = textract_client.start_document_text_detection(
            DocumentLocation=document_location,
            NotificationChannel={
                "SNSTopicArn": SNS_TOPIC_ARN,
                "RoleArn": TEXTRACT_ROLE_ARN,
            },
        )
        print(
            f"Started Textract job with ID: {response['JobId']} for document: s3://{bucket}/{key}"
        )
        return {"statusCode": 200, "body": json.dumps("Textract job started.")}
    except Exception as e:
        print(f"Error starting Textract job: {e}")
        raise e
