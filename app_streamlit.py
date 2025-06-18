import streamlit as st
import requests
import json
import pandas as pd

# --- ページ設定とAPI URL ---
st.set_page_config(
    page_title="QA-Master | AI自動問答生成", page_icon="💡", layout="wide"
)

API_URL = "https://vedtxkcx72.execute-api.us-east-1.amazonaws.com/prod/"

# --- デザイン用カスタムCSS ---
st.markdown(
    """
<style>
    [data-testid="stAppViewContainer"] { background: linear-gradient(180deg, #001f3f, #000020); }
    [data-testid="stSidebar"] { background: rgba(38, 39, 48, 0.4); backdrop-filter: blur(10px); border-right: 1px solid rgba(255, 255, 255, 0.1); }
    .main-container { background: rgba(38, 39, 48, 0.4); backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.1); padding: 2rem; border-radius: 1rem; margin-bottom: 1rem; }
    .stButton > button { background: linear-gradient(90deg, #0072ff, #00c6ff); color: white; border: none; transition: all 0.3s; }
    .stButton > button:hover { opacity: 0.9; box-shadow: 0 0 15px #00c6ff; }
    [data-testid="stExpander"] { background: rgba(255, 255, 255, 0.08); border-radius: 0.5rem; border: 1px solid rgba(255, 255, 255, 0.1); }
    h1, h2, h3 { color: #87CEFA; }
</style>
""",
    unsafe_allow_html=True,
)


# --- session_stateの初期化 ---
if 'page' not in st.session_state:
    st.session_state.page = "QA生成"
if 'selected_qa_set' not in st.session_state:
    st.session_state.selected_qa_set = None
if 'quiz_results' not in st.session_state:
    st.session_state.quiz_results = None

# --- サイドバー ---
with st.sidebar:
    st.title("QA-Master 💡")
    st.markdown("---")
    
    # クイズが選択されている時だけ「クイズ受験」をメニューに追加
    page_options = ["QA生成", "QA管理"]
    if st.session_state.selected_qa_set is not None:
        page_options.append("クイズ受験")
    
    # st.session_state.pageを直接更新
    st.session_state.page = st.radio(
        "メニュー", 
        page_options, 
        index=page_options.index(st.session_state.page), # 現在のページを選択状態に保つ
        label_visibility="hidden"
    )

    st.markdown("---")
    
    # QA生成ページ用の設定
    if st.session_state.page == "QA生成":
        st.markdown("## ⚙️ 生成設定")
        st.session_state.num_q = st.slider("生成する問題数", 1, 10, 5)
        difficulty_map = {"易しい": "易", "普通": "中", "難しい": "難"}
        selected_difficulty_label = st.radio("難易度", list(difficulty_map.keys()), index=1)
        st.session_state.difficulty_code = difficulty_map[selected_difficulty_label]
    
    st.info("AIが講義内容から問題と回答を自動で作成します。")


# ============================
# 1. QA生成ページ
# ============================
if page == "QA生成":
    st.header("1. QAを生成する")
    st.markdown('<div class="main-container">', unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        theme_input = st.text_input("テーマ名", placeholder="例：循環器内科")
    with col2:
        # st.number_inputで数値のみ入力できるようにする
        lecture_number_input = st.number_input(
            "講義回数（任意）",
            min_value=1,
            step=1,
            placeholder="例: 3 (「第3回」の場合)",
        )

    lecture_input = st.text_area(
        "**講義内容のテキストをここに貼り付け**",
        height=250,
        placeholder="講義の文字起こしやノートをここに貼り付けます...",
        label_visibility="visible",
    )
    if st.button("この内容でQAを生成する", type="primary", use_container_width=True):
        if not lecture_input:
            st.warning("講義内容を入力してください。")
        elif not theme_input:
            st.warning("テーマ名を入力してください")
        else:
            with st.spinner("AIが問題を生成中です..."):
                payload = {
                    "lecture_text": lecture_input,
                    "num_questions": st.session_state.num_q,
                    "difficulty": st.session_state.difficulty_code,
                    "theme": theme_input,
                    "lecture_number": lecture_number_input,
                }
                try:
                    response = requests.post(
                        f"{API_URL}generate", json=payload, timeout=180
                    )
                    response.raise_for_status()
                    st.session_state.generated_qa = response.json().get("qa_set", [])
                    st.success("QAが生成されました！")
                    st.balloons()

                    # QA管理ページのキャッシュを削除して、次回の表示で最新化する
                    if "qa_list" in st.session_state:
                        del st.session_state.qa_list

                except requests.exceptions.RequestException as e:
                    st.error(f"APIへの接続中にエラーが発生しました: {e}")
                except json.JSONDecodeError:
                    st.error(
                        f"APIからの応答が不正な形式です。APIのログを確認してください。 応答: {response.text}"
                    )
    st.markdown("</div>", unsafe_allow_html=True)

    if "generated_qa" in st.session_state and st.session_state.generated_qa:
        st.markdown("---")
        st.header("生成結果（ここで回答も試せます）")
        for qa in st.session_state.generated_qa:
            q_id = qa.get("question_id", qa.get("question", "")[:10])

            st.subheader(
                f"問{qa.get('question_id', '')} ({qa.get('difficulty', '')}) - {qa.get('type', qa.get('answer_type', 'N/A'))}"
            )
            st.write(qa.get("question", ""))

            if qa.get("type", qa.get("answer_type")) == "一択選択式":
                options = qa.get("options", [])
                st.radio(
                    "選択肢",
                    options,
                    key=f"q_{q_id}",
                    label_visibility="collapsed",
                    index=None,
                )

            with st.expander("答えと解説を見る"):
                st.markdown(
                    f"**正解:** {qa.get('answer', qa.get('correct_answer', 'N/A'))}"
                )
                st.markdown(f"**解説:** {qa.get('explanation', 'N/A')}")
        st.markdown("---")


# ============================
# 2. QA管理ページ
# ============================
elif page == "QA管理":
    st.header("2. 保存済みQAを管理する")
    st.markdown("##### 絞り込み検索")

    # 検索用の入力ウィジェットを横に並べる
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

    # 検索ボタンとクリアボタン
    col_search, col_clear, _ = st.columns([1, 1, 4])
    with col_search:
        # 検索ボタンは API 呼び出しのトリガーにはせず、UI上の目印として配置
        st.button("検索", use_container_width=True, type="primary")
    with col_clear:
        if st.button("クリア", use_container_width=True):
            # 検索条件をクリアしてページを再実行
            st.session_state.filter_theme_input = ""
            st.session_state.filter_lecture_num_input = 1  # number_inputの初期化
            st.rerun()
    st.markdown("---")

    # if st.button("一覧を再読み込み", use_container_width=True):
    #     if "qa_list" in st.session_state:
    #         del st.session_state.qa_list
    #     st.rerun()

    try:
        # 1. 検索パラメータを準備する
        params = {}
        if filter_theme:  # テーマ入力欄に何か入力されていれば
            params["theme"] = filter_theme
        if filter_lecture_num:  # 講義回数入力欄に何か入力されていれば
            params["lecture_number"] = filter_lecture_num

        # 2. 準備したパラメータを使ってAPIを呼び出す
        with st.spinner("QAを読み込んでいます..."):
            response = requests.get(f"{API_URL}qas", params=params, timeout=60)
            response.raise_for_status()
            qas = response.json()

        # 3. 取得した結果を表示する (この部分は変更なし)
        if not qas:
            st.info("該当するQAセットはありません。")
        else:
            st.info(f"{len(qas)}件のQAセットが見つかりました。")
            st.markdown("---")

            for item in qas:
                qa_set_id = item["qa_set_id"]
                # テーマと回数を表示に追加
                display_title = f"テーマ: {item.get('theme', 'N/A')} | 第{item.get('lecture_number', '?')}回 | ID: `{qa_set_id}`"

                with st.expander(display_title):
                    qa_data = item.get("qa_data", {}).get("qa_set", [])
                    if qa_data:
                        df = pd.DataFrame(qa_data)
                        st.dataframe(df)
                    else:
                        st.write("このセットにはQAデータがありません。")

                    # --- ▼▼▼ ここが変更点です ▼▼▼ ---
                    # ボタンを横に並べるために、列(columns)を作成します
                    col1, col2 = st.columns([4, 1]) # 4:1の比率で列を分割

                    # 1列目に「回答する」ボタンを配置
                    with col1:
                        if st.button("このクイズに回答する", key=f"start_{qa_set_id}", type="primary", use_container_width=True):
                            st.session_state.selected_qa_set = item
                            st.session_state.quiz_results = None # 前回の結果をリセット
                            st.session_state.page = "クイズ受験"
                            st.rerun()

                    # 2列目に「削除」ボタンを配置
                    with col2:
                        if st.button("削除", key=f"delete_{qa_set_id}", type="secondary", use_container_width=True):
                            delete_url = f"{API_URL}qas/{qa_set_id}"
                            delete_response = requests.delete(delete_url)
                            if delete_response.status_code == 204:
                                st.success(f"ID: {qa_set_id} を削除しました。")
                                # ページをリフレッシュしてリストを更新
                                st.rerun()
                            else:
                                st.error(f"削除に失敗しました。ステータスコード: {delete_response.status_code}")

    except Exception as e:
        st.error(f"QA一覧の取得中にエラーが発生しました: {e}")
# ============================
# 3. クイズ受験ページ
# ============================
elif st.session_state.page == "クイズ受験":
    # クイズが選択されていなければ、管理ページに戻るよう促す
    if st.session_state.selected_qa_set is None:
        st.warning("「QA管理」ページから回答したいクイズを選択してください。")
        st.stop()
    
    selected_set = st.session_state.selected_qa_set
    st.header(f"📝 クイズ受験：{selected_set.get('theme', '')} - 第{selected_set.get('lecture_number', '?')}回")
    st.markdown('<div class="main-container">', unsafe_allow_html=True)

    qa_set = selected_set.get("qa_data", {}).get("qa_set", [])

    # 回答フォーム
    with st.form("quiz_form"):
        user_answers_payload = []
        # st.session_stateにユーザーの回答を保存するための準備
        if 'user_answers_display' not in st.session_state:
            st.session_state.user_answers_display = {}

        for i, qa in enumerate(qa_set):
            q_id = qa.get("question_id", i)
            st.subheader(f"問{q_id}: {qa.get('question', '')}")
            
            answer = ""
            if qa.get("type") == "一択選択式":
                answer = st.radio("選択肢", qa.get("options", []), key=f"ans_{q_id}", label_visibility="collapsed", index=None)
            else:
                answer = st.text_area("あなたの回答", key=f"ans_{q_id}")

            is_flagged = st.checkbox("この問題を保留する 🏳️", key=f"flag_{q_id}")
            user_answers_payload.append({"question_id": q_id, "answer": answer, "is_flagged": is_flagged})
            st.session_state.user_answers_display[q_id] = answer # 表示用に回答を保存
            st.markdown("---")
        
        submitted = st.form_submit_button("回答を提出して採点する", use_container_width=True, type="primary")

    st.markdown('</div>', unsafe_allow_html=True)

    # フォームが提出されたら採点APIを呼び出す
    if submitted:
        with st.spinner("採点中です..."):
            qa_set_id = selected_set['qa_set_id']
            api_url = f"{API_URL}qas/{qa_set_id}/submit"
            try:
                response = requests.post(api_url, json={"answers": user_answers_payload}, timeout=60)
                response.raise_for_status()
                st.success("採点が完了しました！")
                st.session_state.quiz_results = response.json()
            except Exception as e:
                st.error(f"採点中にエラーが発生しました: {e}")

    # 採点結果があれば表示する
    if st.session_state.quiz_results:
        st.markdown("---")
        st.header("✨ 採点結果")
        results = st.session_state.quiz_results
        score = results.get('score', 0)
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric(label="正答率", value=f"{score:.1f} %")
        with col2:
            st.metric(label="正解数", value=f"{results.get('correct_count', 0)} / {results.get('total_count', 0)}")
        
        st.progress(int(score))
        st.markdown("---")

        st.markdown("### 各問題の結果")
        for i, qa in enumerate(qa_set):
            q_id = qa.get("question_id", i)
            result_detail = results['results'][i]
            status_icon = "✅" if result_detail['is_correct'] else "❌"
            if result_detail['is_flagged']: status_icon = "🏳️"

            with st.expander(f"{status_icon} 問{q_id}: {qa.get('question')}"):
                st.markdown(f"**あなたの回答:** {st.session_state.user_answers_display.get(q_id, '（未回答）')}")
                st.markdown(f"**模範解答:** {qa.get('correct_answer')}")
                if qa.get('type') == '記述式':
                    st.markdown(f"**必須キーワード:** `{'`, `'.join(qa.get('scoring_keywords', []))}`")
                st.markdown(f"**解説:** {qa.get('explanation')}")