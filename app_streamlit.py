import streamlit as st
import requests
import json
import pandas as pd

# --- ページ設定とAPI URL ---
st.set_page_config(
    page_title="QA-Master | AI自動問答生成",
    page_icon="💡",
    layout="wide"
)

API_URL = "https://vedtxkcx72.execute-api.us-east-1.amazonaws.com/prod/" 

# --- デザイン用カスタムCSS ---
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: linear-gradient(180deg, #001f3f, #000020); }
    [data-testid="stSidebar"] { background: rgba(38, 39, 48, 0.4); backdrop-filter: blur(10px); border-right: 1px solid rgba(255, 255, 255, 0.1); }
    .main-container { background: rgba(38, 39, 48, 0.4); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); padding: 2rem; border-radius: 1rem; margin-bottom: 1rem; }
    .stButton > button { background: linear-gradient(90deg, #0072ff, #00c6ff); color: white; border: none; transition: all 0.3s; }
    .stButton > button:hover { opacity: 0.9; box-shadow: 0 0 15px #00c6ff; }
    [data-testid="stExpander"] { background: rgba(255, 255, 255, 0.08); border-radius: 0.5rem; border: 1px solid rgba(255, 255, 255, 0.1); }
    h1, h2, h3 { color: #87CEFA; }
</style>
""", unsafe_allow_html=True)


# --- サイドバー (ページ選択機能) ---
with st.sidebar:
    st.title("QA-Master 💡")
    st.markdown("---")
    page = st.radio("メニュー", ["QA生成", "QA管理"], label_visibility="hidden")
    st.markdown("---")

    if page == "QA生成":
        st.markdown("## ⚙️ 生成設定")
        num_q = st.slider("生成する問題数", 1, 10, 5, key="num_q")
        difficulty_map = {"易しい": "易", "普通": "中", "難しい": "難"}
        selected_difficulty_label = st.radio("難易度", list(difficulty_map.keys()), index=1, key="difficulty")
        st.session_state.difficulty_code = difficulty_map[selected_difficulty_label]
    
    st.markdown("---")
    st.info("AIが講義内容から問題と回答を自動で作成します。")


# ============================
# 1. QA生成ページ
# ============================
if page == "QA生成":
    st.header("1. QAを生成する")
    st.markdown('<div class="main-container">', unsafe_allow_html=True)
    lecture_input = st.text_area(
        "**講義内容のテキストをここに貼り付け**", 
        height=250, 
        placeholder="講義の文字起こしやノートをここに貼り付けます...",
        label_visibility="visible"
    )
    if st.button("この内容でQAを生成する", type="primary", use_container_width=True):
        if not lecture_input:
            st.warning("講義内容を入力してください。")
        else:
            with st.spinner("AIが問題を生成中です..."):
                payload = {
                    "lecture_text": lecture_input,
                    "num_questions": st.session_state.num_q,
                    "difficulty": st.session_state.difficulty_code
                }
                try:
                    response = requests.post(f"{API_URL}generate", json=payload, timeout=180)
                    response.raise_for_status() 
                    st.session_state.generated_qa = response.json().get('qa_set', [])
                    st.success("QAが生成されました！")
                    st.balloons()
                    
                    # ★★★ 修正点2: QA管理ページのキャッシュを削除して、次回の表示で最新化する ★★★
                    if 'qa_list' in st.session_state:
                        del st.session_state.qa_list

                except requests.exceptions.RequestException as e:
                    st.error(f"APIへの接続中にエラーが発生しました: {e}")
                except json.JSONDecodeError:
                    st.error(f"APIからの応答が不正な形式です。APIのログを確認してください。 応答: {response.text}")
    st.markdown('</div>', unsafe_allow_html=True)

    # ★★★ 修正点3: インタラクティブなプレビュー機能を完全に復活 ★★★
    if 'generated_qa' in st.session_state and st.session_state.generated_qa:
        st.markdown("---")
        st.header("生成結果（ここで回答も試せます）")
        for qa in st.session_state.generated_qa:
            q_id = qa.get('question_id', qa.get('question', '')[:10]) 

            st.subheader(f"問{qa.get('question_id', '')} ({qa.get('difficulty', '')}) - {qa.get('type', qa.get('answer_type', 'N/A'))}")
            st.write(qa.get('question', ''))

            if qa.get('type', qa.get('answer_type')) == '一択選択式':
                options = qa.get('options', [])
                st.radio("選択肢", options, key=f"q_{q_id}", label_visibility="collapsed", index=None)
            
            with st.expander("答えと解説を見る"):
                st.markdown(f"**正解:** {qa.get('answer', qa.get('correct_answer', 'N/A'))}")
                st.markdown(f"**解説:** {qa.get('explanation', 'N/A')}")
        st.markdown("---")


# ============================
# 2. QA管理ページ
# ============================
elif page == "QA管理":
    st.header("2. 保存済みQAを管理する")

    # ★★★ 修正点1: st.rerun() に変更 ★★★
    if st.button("一覧を再読み込み", use_container_width=True):
        if 'qa_list' in st.session_state:
            del st.session_state.qa_list
        st.rerun()

    try:
        if 'qa_list' not in st.session_state:
            with st.spinner("保存されたQAを読み込んでいます..."):
                response = requests.get(f"{API_URL}qas", timeout=60)
                response.raise_for_status()
                st.session_state.qa_list = response.json()
        
        qas = st.session_state.get('qa_list', [])

        if not qas:
            st.info("保存されているQAはありません。「QA生成」ページで新しいQAを作成してください。")
        else:
            st.info(f"{len(qas)}件のQAセットが見つかりました。")
            st.markdown("---")
            
            for item in qas:
                qa_set_id = item['qa_set_id']
                with st.expander(f"QAセットID: `{qa_set_id}` (テキスト冒頭: {item.get('lecture_text_head', 'N/A')}...)"):
                    
                    qa_data = item.get('qa_data', {}).get('qa_set', [])
                    if qa_data:
                        df = pd.DataFrame(qa_data)
                        st.dataframe(df)
                    else:
                        st.write("このセットにはQAデータがありません。")

                    if st.button("このQAセットを削除", key=qa_set_id, type="secondary"):
                        delete_url = f"{API_URL}qas/{qa_set_id}"
                        delete_response = requests.delete(delete_url)
                        if delete_response.status_code == 204:
                            st.success(f"ID: {qa_set_id} を削除しました。")
                            if 'qa_list' in st.session_state:
                                del st.session_state.qa_list
                            # ★★★ 修正点1: st.rerun() に変更 ★★★
                            st.rerun()
                        else:
                            st.error(f"削除に失敗しました。ステータスコード: {delete_response.status_code}")
                            
    except Exception as e:
        st.error(f"QA一覧の取得中にエラーが発生しました: {e}")