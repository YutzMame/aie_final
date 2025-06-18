# lambda/main.py 

import json
import os
import boto3
from botocore.exceptions import ClientError
import traceback

# 環境変数からモデルIDを取得。なければデフォルト値を使用。
MODEL_ID = os.environ.get("MODEL_ID", "amazon.nova-lite-v1:0")

bedrock_runtime = boto3.client(service_name='bedrock-runtime')

def handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    print(f"Using model: {MODEL_ID}")

    try:
        body = json.loads(event['body'])
        lecture_text = body['lecture_text']
        num_questions = body.get('num_questions', 5)
        difficulty = body.get('difficulty', '中')
    except Exception as e:
        print(f"ERROR: Failed to parse request body. {str(e)}")
        return create_error_response(400, f"リクエストの解析に失敗しました: {str(e)}")

    prompt = f"""
あなたは、講義内容から学習者の理解度を測るための問題を作成する専門家です。
以下のルールに従って、与えられた講義内容から質の高いQAセットを作成してください。

# ルール
- 質問形式は「一択選択式」「記述式」をバランス良く含めること。
- {num_questions}個の問題を、難易度「{difficulty}」で作成すること。
- 回答には、なぜそれが正解なのかの短い解説を必ず含めること。
- 出力は必ず指定されたJSON形式のみとし、前後に余計な文章は含めないこと。

# JSON形式
{{
  "qa_set": [
    {{
      "question_id": 1,
      "difficulty": "易",
      "type": "一択選択式",
      "question_text": "質問文",
      "options": ["選択肢A", "選択肢B", "選択肢C", "選択肢D"],
      "answer": "正解の選択肢",
      "explanation": "解説文"
    }}
  ]
}}

---
講義内容:
{lecture_text}
"""
    
    # Bedrockの新しいConverse API形式に合わせたリクエストボディ
    request_body = {
        "anthropic_version": "bedrock-2023-05-31", # Claudeモデルなどを使う場合に推奨されるバージョン指定
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    }

    try:
        # Bedrock APIを呼び出し
        response = bedrock_runtime.invoke_model(
            body=json.dumps(request_body), 
            modelId=MODEL_ID
        )
        
        response_body = json.loads(response.get('body').read())
        # Claude 3などのMessages API形式のモデルからの応答を抽出
        qa_result_text = response_body.get('content')[0].get('text')
        
        # モデルが生成したJSON文字列をPythonオブジェクトに変換
        qa_result_json = json.loads(qa_result_text)
        
        print("Successfully generated QA.")
        return create_success_response(qa_result_json)

    except ClientError as e:
        print(f"ERROR: Bedrock ClientError. {str(e)}")
        return create_error_response(500, f"Bedrockの呼び出し中に権限エラーが発生しました: {e.response['Error']['Message']}")
    except Exception as e:
        print(f"ERROR: An unexpected error occurred. {traceback.format_exc()}")
        return create_error_response(500, f"予期せぬエラーが発生しました: {str(e)}")


def create_success_response(body):
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(body)
    }

def create_error_response(status_code, error_message):
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps({"error": error_message})
    }