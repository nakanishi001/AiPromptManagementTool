
from pathlib import Path

import streamlit as st
from google import genai

PROMPTS_DIR = Path(__file__).parent / "prompts"
PROMPTS_DIR.mkdir(exist_ok=True)
RULES_DIR = Path(__file__).parent / "rules"
RULES_DIR.mkdir(exist_ok=True)


def reset_app_state():
    for key in list(st.session_state.keys()):
        if key != "reset_app":
            del st.session_state[key]


st.set_page_config(page_title="AI指示文管理ツール", layout="wide")
title_column, update_column = st.columns([8, 1])
with title_column:
    st.title("AI指示文管理ツール")
with update_column:
    st.button("更新", key="reset_app", on_click=reset_app_state)


def valid_filename(name):
    return (
        bool(name.strip())
        and Path(name).name == name
        and name not in {".", ".."}
        and not any(c in name for c in '/\\:\x00')
    )


# ----------------------------------------
# AIによる指示文の作成
# ----------------------------------------
st.header("1. AIで指示文を作成")

generation_type = st.radio(
    "生成するもの",
    ["プロンプト", "ルール"],
    horizontal=True,
    key="generation_type",
)

request = st.text_area(
    "作成したい内容の要望",
    placeholder=(
        "例：C言語のソースコードを解析し、全体構造を簡潔に説明させたい。"
        if generation_type == "プロンプト"
        else "例：周辺のソースコードの書式に合わせるルールを作りたい。"
    ),
    height=120,
    key="ai_request",
)

selected_rules = []
if generation_type == "プロンプト":
    st.subheader("オプションルール")
    rule_files = sorted(RULES_DIR.glob("*.md"))

    if not rule_files:
        st.caption("ルールファイルがありません。")
    else:
        rule_columns = st.columns(min(3, len(rule_files)))
        for index, rule_path in enumerate(rule_files):
            with rule_columns[index % len(rule_columns)]:
                if st.checkbox(
                    rule_path.stem,
                    key=f"option_rule_{rule_path.name}",
                ):
                    selected_rules.append(rule_path)

if st.button("AIで指示文を生成", type="primary"):
    if not request.strip():
        st.warning("作成したい内容の要望を入力してください。")
    else:
        try:
            api_key = st.secrets["GEMINI_API_KEY"]
            client = genai.Client(api_key=api_key)

            if generation_type == "プロンプト":
                selected_rule_text = "\n\n".join(
                    f"### {rule_path.stem}\n"
                    f"{rule_path.read_text(encoding='utf-8')}"
                    for rule_path in selected_rules
                )
                if not selected_rule_text:
                    selected_rule_text = "（指定なし）"

                instruction = f"""
あなたは、AIへの指示文を設計するアシスタントです。
ユーザーの要望を実現するための指示文を日本語で作成してください。

条件：
- そのままAIに入力して使える指示文にする
- 必要な作業内容、出力形式、注意事項を整理する
- 不明な条件を勝手に事実として決めつけない
- Markdown形式で出力する
- 指示文そのものだけを出力し、前置きや解説は付けない

適用するオプションルール：
{selected_rule_text}

ユーザーの要望：
{request}
"""
            else:
                instruction = f"""
あなたは、開発作業で再利用するルールを設計するアシスタントです。
ユーザーの要望を実現するためのルールを日本語で作成してください。

条件：
- ルールとして具体的で、再利用できる内容にする
- Markdown形式で出力する
- ルール本文そのものだけを出力し、前置きや解説は付けない
- 不明な条件を勝手に事実として決めつけない

ユーザーの要望：
{request}
"""

            with st.spinner("AIが指示文を作成しています..."):
                response = client.models.generate_content(
                    model="gemini-3.8-flash",
                    contents=instruction,
                )

            if not response.text:
                st.error("AIから文章を取得できませんでした。")
            else:
                st.session_state["generated_prompt"] = response.text
                st.session_state["generated_name"] = "新しい指示文"
                st.session_state["generated_type"] = generation_type

        except Exception as e:
            st.error(
                "生成に失敗しました。APIキー、モデルの利用可否、"
                "インターネット接続、利用制限、選択したルールファイルを確認してください。"
            )
            st.caption(f"エラー詳細：{e}")


if "generated_prompt" in st.session_state:
    generated_type = st.session_state.get("generated_type", "プロンプト")
    st.subheader(f"生成された{generated_type}")
    generated_name = st.text_input(
        "保存するファイル名（拡張子 .md は不要）",
        key="generated_name",
    )
    generated_content = st.text_area(
        "内容を確認・編集",
        key="generated_prompt",
        height=350,
    )

    if st.button(f"生成した{generated_type}をMarkdownに保存"):
        if not valid_filename(generated_name):
            st.error("ファイル名を正しく入力してください。")
        elif not generated_content.strip():
            st.error("指示文の内容が空です。")
        else:
            output_dir = (
                PROMPTS_DIR if generated_type == "プロンプト" else RULES_DIR
            )
            save_path = output_dir / f"{generated_name.strip()}.md"

            if save_path.exists():
                st.error(
                    "同名ファイルが存在します。別の名前を指定してください。"
                )
            else:
                save_path.write_text(
                    generated_content,
                    encoding="utf-8",
                )
                st.success(f"保存しました：{save_path.name}")
                st.rerun()


st.divider()

# ----------------------------------------
# 保存済みMarkdownの検索・編集
# ----------------------------------------
st.header("2. 保存済み指示文の管理")

keyword = st.text_input("検索（ファイル名・本文）").strip().casefold()
prompt_files = sorted(PROMPTS_DIR.glob("*.md"))

if keyword:
    prompt_files = [
        path for path in prompt_files
        if keyword in path.stem.casefold()
        or keyword in path.read_text(encoding="utf-8").casefold()
    ]

st.caption(f"該当件数：{len(prompt_files)} 件")

mode = st.radio(
    "操作",
    ["新規作成", "既存の指示文を編集"],
    horizontal=True,
    key="manage_mode",
)

if mode == "新規作成":
    name = st.text_input("指示文の名前", key="new_name")
    content = st.text_area(
        "指示文の内容",
        height=250,
        key="new_content",
    )

    if st.button("Markdownファイルに保存", key="save_new"):
        if not valid_filename(name):
            st.error("ファイル名を正しく入力してください。")
        elif not content.strip():
            st.error("指示文の内容を入力してください。")
        else:
            save_path = PROMPTS_DIR / f"{name.strip()}.md"
            if save_path.exists():
                st.error("同じ名前のファイルが存在します。")
            else:
                save_path.write_text(content, encoding="utf-8")
                st.success(f"保存しました：{save_path.name}")
                st.rerun()

elif not prompt_files:
    st.info("該当する指示文がありません。")

else:
    selected_path = st.selectbox(
        "編集する指示文",
        prompt_files,
        format_func=lambda path: path.stem,
    )

    content = selected_path.read_text(encoding="utf-8")
    edited_content = st.text_area(
        "指示文の内容",
        value=content,
        height=300,
        key=f"edit_{selected_path.name}",
    )

    st.download_button(
        "指示文をダウンロード",
        data=edited_content,
        file_name=selected_path.name,
        mime="text/markdown",
    )

    if st.button("変更を保存", key="save_edit"):
        selected_path.write_text(edited_content, encoding="utf-8")
        st.success(f"保存しました：{selected_path.name}")
        st.rerun()
