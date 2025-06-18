# app_streamlit.py

import streamlit as st
import requests
import json

API_URL = "https://vedtxkcx72.execute-api.us-east-1.amazonaws.com/prod/" 


st.set_page_config(page_title="QA自動生成システム", layout="wide")
st.title("📝 講義内容QA 自動生成システム")

with st.sidebar:
    st.header("設定")
    num_q = st.slider("生成する問題数", 1, 10, 5)
    difficulty_map = {"易しい": "易", "普通": "中", "難しい": "難"}
    selected_difficulty_label = st.radio("難易度", list(difficulty_map.keys()))
    difficulty_code = difficulty_map[selected_difficulty_label]

lecture_input = st.text_area("ここに講義内容のテキストを貼り付けてください", height=300, placeholder="講義の文字起こしやノートをここに貼り付けます。")

if st.button("QAを生成する", type="primary"):
    if not lecture_input:
        st.warning("講義内容を入力してください。")
    elif "https://xxxxxxxxx" in API_URL:
        st.error("エラー: API_URLをあなたのAPI GatewayのURLに書き換えてください。")
    else:
        with st.spinner("AIが問題を生成中です..."):
            # APIに送信するデータを作成
            payload = {
                "lecture_text": lecture_input,
                "num_questions": num_q,
                "difficulty": difficulty_code
            }
            # APIを呼び出す
            try:
                response = requests.post(f"{API_URL}generate", json=payload, timeout=120) # タイムアウトを120秒に設定
                response.raise_for_status() # エラーがあればここで例外発生

                # 応答をセッションに保存
                st.session_state.qa_data = response.json().get('qa_set', [])
                st.success("QAが生成されました！")

            except requests.exceptions.RequestException as e:
                st.error(f"APIへの接続中にエラーが発生しました: {e}")
            except json.JSONDecodeError:
                st.error(f"APIからの応答が不正な形式です。APIのログを確認してください。 応答: {response.text}")

# 生成されたQAがあれば表示
if 'qa_data' in st.session_state and st.session_state.qa_data:
    st.markdown("---")
    st.header("生成されたQA")
    for qa in st.session_state.qa_data:
        st.subheader(f"問{qa.get('question_id', '')} ({qa.get('difficulty', '')}) - {qa.get('type', '')}")
        st.write(qa.get('question_text', ''))
        if qa.get('type') == '一択選択式':
            options = qa.get('options', [])
            # st.radioは選択肢が同じだとキーエラーになるため、ユニークなキーを設定
            st.radio("選択肢", options, key=f"q{qa.get('question_id')}_{options[0]}", label_visibility="collapsed")

        with st.expander("答えと解説を見る"):
            st.markdown(f"**正解:** {qa.get('answer', 'N/A')}")
            st.markdown(f"**解説:** {qa.get('explanation', 'N/A')}")