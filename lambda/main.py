# lambda/main.py
import json
import boto3
import os

bedrock_runtime = boto3.client(
    service_name='bedrock-runtime', 
    region_name='us-east-1' # Bedrockの利用可能なリージョン
)

def handler(event, context):
    try:
        body = json.loads(event['body'])
        lecture_text = body['lecture_text']
        num_questions = body.get('num_questions', 5)
        difficulty = body.get('difficulty', '中')
    except Exception as e:
        return {'statusCode': 400, 'body': json.dumps(f"リクエストの解析に失敗しました: {str(e)}")}

    prompt = f"""
あなたは、講義内容から学習者の理解度を測るための問題を作成する専門家です。
以下のルールに従って、与えられた講義内容から質の高いQAセットを作成してください。

# ルール
- 質問形式は「一択選択式」「記述式」をバランス良く含めること。
- {num_questions}個の問題を、難易度「{difficulty}」で作成すること。
- 回答には、なぜそれが正解なのかの短い解説を必ず含めること。
- 出力は必ず指定されたJSON形式とすること。

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

    # Nova Liteを使用
    model_id = 'amazon.nova-lite-v1:0'
    body = json.dumps({
        "inputText": prompt,
        "textGenerationConfig": { "maxTokenCount": 4096, "stopSequences": [], "temperature": 0.7, "topP": 0.9 }
    })

    try:
        response = bedrock_runtime.invoke_model(body=body, modelId=model_id)
        response_body = json.loads(response.get('body').read())
        qa_result = response_body.get('results')[0].get('outputText')

        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': qa_result
        }
    except Exception as e:
        return {'statusCode': 500, 'body': json.dumps(f"Bedrockの呼び出し中にエラーが発生しました: {str(e)}")}
