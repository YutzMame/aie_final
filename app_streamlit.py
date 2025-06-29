import streamlit as st
import requests
import json
import pandas as pd
import base64

# --- ページ設定とAPI URL ---
st.set_page_config(
    page_title="QA作成ツール | AI自動問答生成", page_icon="💡", layout="wide"
)

# CDKデプロイ後に、Outputsから正しいAPI URLを取得して設定してください
API_URL = "https://vedtxkcx72.execute-api.us-east-1.amazonaws.com/prod/" 

# --- デザイン用カスタムCSS ---
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: linear-gradient(180deg, #001f3f, #000020); }
    [data-testid="stSidebar"] { background: rgba(38, 39, 48, 0.4); backdrop-filter: blur(10px); }
    .main-container { background: rgba(38, 39, 48, 0.4); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); padding: 2rem; border-radius: 1rem; }
    .stButton > button { background: linear-gradient(90deg, #0072ff, #00c6ff); color: white; border: none; }
    .stButton > button:hover { opacity: 0.9; box-shadow: 0 0 15px #00c6ff; }
    h1, h2, h3 { color: #87CEFA; }
</style>
""", unsafe_allow_html=True)

# --- session_stateの初期化 ---
if "page" not in st.session_state:
    st.session_state.page = "QA生成"
if "selected_qa_set" not in st.session_state:
    st.session_state.selected_qa_set = None
if "quiz_results" not in st.session_state:
    st.session_state.quiz_results = None

# --- サイドバー ---
with st.sidebar:
    st.title("QA作成ツール")
    st.markdown("---")
    page_options = ["QA生成", "QA管理"]
    if st.session_state.selected_qa_set is not None:
        page_options.append("クイズ受験")
    st.session_state.page = st.radio("メニュー", page_options, index=page_options.index(st.session_state.page), label_visibility="collapsed")
    st.markdown("---")
    if st.session_state.page == "QA生成":
        st.markdown("## ⚙️ 生成設定")
        st.session_state.num_q = st.slider("生成する問題数", 1, 10, 5)
        difficulty_map = {"易しい": "易", "普通": "中", "難しい": "難"}
        selected_difficulty_label = st.radio("難易度", list(difficulty_map.keys()), index=1)
        st.session_state.difficulty_code = difficulty_map[selected_difficulty_label]
    st.info("講義資料のPDFから問題と回答を自動で作成します。")

# ============================
# 1. QA生成ページ
# ============================
if st.session_state.page == "QA生成":
    st.header("1. PDFからQAを生成する")
    st.markdown('<div class="main-container">', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        theme_input = st.text_input("テーマ名", placeholder="例：サーバーレスアーキテクチャ")
    with col2:
        lecture_number_input = st.number_input("講義回数（必須）", min_value=1, step=1, placeholder="例: 5")

    st.markdown("---")
    
    # PDFアップロード機能に一本化
    uploaded_file = st.file_uploader(
        "講義資料のPDFファイルをアップロード",
        type=["pdf"],
        label_visibility="visible"
    )

    if st.button("PDFからQAを生成", use_container_width=True, type="primary"):
        if uploaded_file is None:
            st.warning("PDFファイルをアップロードしてください。")
        elif not theme_input or not lecture_number_input:
            st.warning("テーマ名と講義回数を入力してください。")
        else:
            with st.spinner("ファイルをアップロードしています..."):
                try:
                    # 1. メタデータ付きの事前署名付きPOST情報を取得
                    get_url_payload = {
                        "file_name": uploaded_file.name,
                        "theme": theme_input,
                        "lecture_number": int(lecture_number_input),
                        "num_questions": st.session_state.num_q,
                        "difficulty": st.session_state.difficulty_code,
                    }
                    get_url_response = requests.post(f"{API_URL.rstrip('/')}/get-upload-url", json=get_url_payload)
                    get_url_response.raise_for_status()
                    post_info = get_url_response.json()

                    # 2. S3にファイルをフォーム形式でPOST
                    files = {"file": uploaded_file.getvalue()}
                    upload_response = requests.post(post_info['url'], data=post_info['fields'], files=files)
                    upload_response.raise_for_status()

                    # 3. 成功メッセージを表示
                    st.success("ファイルのアップロードが完了しました。")
                    st.info("バックグラウンドで文字抽出とQA生成が開始されます。処理には数分かかる場合があります。しばらくしてから「QA管理」ページで結果を確認してください。")
                    st.balloons()

                except Exception as e:
                    import traceback
                    st.error(f"処理中に予期せぬエラーが発生しました: {e}")
                    st.code(f"""
                    エラータイプ: {type(e).__name__}
                    エラーメッセージ: {e}
                    --- トレースバック ---
                    {traceback.format_exc()}
                    """)

    st.markdown("</div>", unsafe_allow_html=True)
# ============================
# 2. QA管理ページ
# ============================
elif st.session_state.page == "QA管理":
    st.header("2. 保存済みQAを管理する")
    st.markdown("##### 絞り込み検索")

    col1, col2 = st.columns([3, 2])
    with col1:
        filter_theme = st.text_input("テーマ名で検索", placeholder="例：循環器内科")
    with col2:
        filter_lecture_num = st.number_input(
            "講義回数で検索",
            min_value=1,
            step=1,
            format="%d",
            placeholder="未入力の場合は全回数を表示",
        )

    col_search, col_clear, _ = st.columns([1, 1, 4])
    with col_search:
        st.button("検索", use_container_width=True, type="primary")
    with col_clear:
        if st.button("クリア", use_container_width=True):
            st.rerun()

    st.markdown("---")

    try:
        params = {}
        if filter_theme:
            params["theme"] = filter_theme
        if filter_lecture_num:
            params["lecture_number"] = filter_lecture_num

        with st.spinner("QAを読み込んでいます..."):
            response = requests.get(
                f"{API_URL.rstrip('/')}/qas", params=params, timeout=60
            )
            response.raise_for_status()
            qas = response.json()

        if not qas:
            st.info("該当するQAセットはありません。")
        else:
            st.info(f"{len(qas)}件のQAセットが見つかりました。")
            st.markdown("---")
            for item in qas:
                qa_set_id = item["qa_set_id"]
                display_title = f"テーマ: {item.get('theme', 'N/A')} | 第{item.get('lecture_number', '?')}回 | ID: `{qa_set_id}`"
                with st.expander(display_title):
                    qa_data = item.get("qa_data", {}).get("qa_set", [])
                    if qa_data:
                        st.dataframe(pd.DataFrame(qa_data))
                    else:
                        st.write("このセットにはQAデータがありません。")

                    col1, col2 = st.columns([4, 1])
                    with col1:
                        if st.button(
                            "このクイズに回答する",
                            key=f"start_{qa_set_id}",
                            type="primary",
                            use_container_width=True,
                        ):
                            st.session_state.selected_qa_set = item
                            st.session_state.quiz_results = None
                            st.session_state.page = "クイズ受験"
                            st.rerun()
                    with col2:
                        if st.button(
                            "削除",
                            key=f"delete_{qa_set_id}",
                            type="secondary",
                            use_container_width=True,
                        ):
                            delete_url = f"{API_URL.rstrip('/')}/qas/{qa_set_id}"
                            delete_response = requests.delete(delete_url)
                            if delete_response.status_code == 204:
                                st.success(f"ID: {qa_set_id} を削除しました。")
                                st.rerun()
                            else:
                                st.error(
                                    f"削除に失敗しました。ステータスコード: {delete_response.status_code}"
                                )
    except Exception as e:
        st.error(f"QA一覧の取得中にエラーが発生しました: {e}")

# ============================
# 3. クイズ受験ページ
# ============================
elif st.session_state.page == "クイズ受験":
    if st.session_state.selected_qa_set is None:
        st.warning("「QA管理」ページから回答したいクイズを選択してください。")
        st.stop()

    selected_set = st.session_state.selected_qa_set
    st.header(
        f"📝 クイズ受験：{selected_set.get('theme', '')} - 第{selected_set.get('lecture_number', '?')}回"
    )
    st.markdown('<div class="main-container">', unsafe_allow_html=True)

    qa_set = selected_set.get("qa_data", {}).get("qa_set", [])

    with st.form("quiz_form"):
        user_answers_payload = []
        if "user_answers_display" not in st.session_state:
            st.session_state.user_answers_display = {}

        for i, qa in enumerate(qa_set):
            q_id = qa.get("question_id", i)
            st.subheader(f"問{q_id}: {qa.get('question', '')}")

            answer = ""
            if qa.get("type") == "一択選択式":
                answer = st.radio(
                    "選択肢",
                    qa.get("options", []),
                    key=f"ans_{q_id}",
                    label_visibility="collapsed",
                    index=None,
                )
            else:
                answer = st.text_area("あなたの回答", key=f"ans_{q_id}")

            is_flagged = st.checkbox("この問題を保留する 🏳️", key=f"flag_{q_id}")
            user_answers_payload.append(
                {"question_id": q_id, "answer": answer, "is_flagged": is_flagged}
            )
            st.session_state.user_answers_display[q_id] = answer
            st.markdown("---")

        submitted = st.form_submit_button(
            "回答を提出して採点する", use_container_width=True, type="primary"
        )

    st.markdown("</div>", unsafe_allow_html=True)

    if submitted:
        with st.spinner("採点中です..."):
            qa_set_id = selected_set["qa_set_id"]
            api_url = f"{API_URL.rstrip('/')}/qas/{qa_set_id}/submit"
            try:
                response = requests.post(
                    api_url, json={"answers": user_answers_payload}, timeout=60
                )
                response.raise_for_status()
                st.success("採点が完了しました！")
                st.session_state.quiz_results = response.json()
            except Exception as e:
                st.error(f"採点中にエラーが発生しました: {e}")

    if st.session_state.quiz_results:
        st.markdown("---")
        st.header("✨ 採点結果")
        results = st.session_state.quiz_results
        score = results.get("score", 0)

        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="正答率", value=f"{score:.1f} %")
        with col2:
            st.metric(
                label="正解数",
                value=f"{results.get('correct_count', 0)} / {results.get('total_count', 0)}",
            )

        st.progress(int(score))
        st.markdown("---")

        st.markdown("### 各問題の結果")
        for i, qa in enumerate(qa_set):
            q_id = qa.get("question_id", i)
            result_detail = results.get("results", [])[i]
            status_icon = "✅" if result_detail.get("is_correct") else "❌"
            if result_detail.get("is_flagged"):
                status_icon = "🏳️"

            with st.expander(f"{status_icon} 問{q_id}: {qa.get('question')}"):
                st.markdown(
                    f"**あなたの回答:** {st.session_state.user_answers_display.get(q_id, '（未回答）')}"
                )
                st.markdown(f"**模範解答:** {qa.get('correct_answer')}")
                if qa.get("type") == "記述式":
                    st.markdown(
                        f"**必須キーワード:** `{'`, `'.join(qa.get('scoring_keywords', []))}`"
                    )
                st.markdown(f"**解説:** {qa.get('explanation')}")
