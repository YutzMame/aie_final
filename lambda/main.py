# lambda/main.py (ユーザーガイド準拠 最終確定版)

import json
import os
import boto3
from botocore.exceptions import ClientError
import traceback

# 環境変数からモデルIDを取得。CDK側で "us.amazon.nova-lite-v1:0" が設定される
MODEL_ID = os.environ.get("MODEL_ID", "us.amazon.nova-lite-v1:0") 
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
bedrock_runtime = boto3.client(service_name='bedrock-runtime', region_name=AWS_REGION)

def handler(event, context):
    print(f"Received event: {json.dumps(event)}")
    print(f"Using model: {MODEL_ID} in region: {AWS_REGION}")

    try:
        body = json.loads(event['body'])
        lecture_text = body['lecture_text']
        num_questions = body.get('num_questions', 5)
        difficulty = body.get('difficulty', '中')
    except Exception as e:
        return create_error_response(400, f"リクエストの解析に失敗しました: {str(e)}")

    # システムプロンプト：モデルの役割を定義
    system_prompt = f"""
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
"""
    # ユーザープロンプト：モデルに具体的な指示を与える
    user_prompt = f"--- 講義内容 ---\n{lecture_text}"
    
    # ★★★ ユーザーガイドに基づく、Novaモデルが期待する正しいリクエストボディ ★★★
    request_body = {
        "schemaVersion": "messages-v1",
        "system": [{"text": system_prompt}],
        "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
        "inferenceConfig": {
            "maxTokens": 4096,
            "stopSequences": [],
            "temperature": 0.7,
            "topP": 0.9
        }
    }

    try:
        print(f"Calling Bedrock with payload: {json.dumps(request_body)}")
        response = bedrock_runtime.invoke_model(
            body=json.dumps(request_body), 
            modelId=MODEL_ID
        )
        
        response_body = json.loads(response.get('body').read())
        # 新しい応答形式に合わせて結果を抽出
        qa_result_text = response_body.get('output', {}).get('message', {}).get('content', [{}])[0].get('text')
        
        if not qa_result_text:
            raise Exception("モデルの応答からテキストを抽出できませんでした。")

        # モデルの応答からJSON部分だけを安全に抽出
        # モデルがJSONの前後に説明などをつけてしまう場合があるため
        json_match = re.search(r'\{.*\}', qa_result_text, re.DOTALL)
        if json_match:
            qa_result_json = json.loads(json_match.group(0))
        else:
            raise Exception("モデルの応答から有効なJSONを抽出できませんでした。")

        print("Successfully generated QA.")
        return create_success_response(qa_result_json)

    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message_detail = e.response['Error']['Message']
        print(f"ERROR: Bedrock ClientError ({error_code}): {error_message_detail}")
        if error_code == 'AccessDeniedException':
            error_message = f"Bedrockモデル {MODEL_ID} へのアクセスが拒否されました。Bedrockコンソールでモデルアクセスが有効か確認してください。"
        else:
            error_message = f"Bedrockの呼び出し中にエラーが発生しました: {error_message_detail}"
        return create_error_response(500, error_message)
    except Exception as e:
        import traceback
        print(f"ERROR: An unexpected error occurred. {traceback.format_exc()}")
        return create_error_response(500, f"予期せぬエラーが発生しました: {str(e)}")


def create_success_response(body):
    return {
        'statusCode': 200,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps(body, ensure_ascii=False)
    }

def create_error_response(status_code, error_message):
    return {
        'statusCode': status_code,
        'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
        'body': json.dumps({"error": error_message}, ensure_ascii=False)
    }