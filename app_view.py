import streamlit as st

from gui_config import (
    DEFAULT_GUI_CONFIG,
    generate_gui_config,
    load_gui_config,
    save_gui_config,
)
from prompt_service import (
    INPUT_PARAMETERS_DIR,
    PROMPTS_DIR,
    RULES_DIR,
    generate_instruction,
    initialize_storage,
    list_markdown_files,
    overwrite_markdown,
    read_markdown,
    save_markdown,
    search_prompts,
    valid_filename,
)
from ui_renderer import append_custom_values, render_custom_fields


def reset_app_state():
    for key in list(st.session_state.keys()):
        if key != "reset_app":
            del st.session_state[key]
    st.session_state["ai_request"] = ""


def update_request_from_input_parameter(parameter_name, parameter_text):
    request = st.session_state.get("ai_request", "")
    parameter_key = f"input_parameter_{parameter_name}"

    if st.session_state.get(parameter_key):
        if parameter_text and parameter_text not in request:
            request = f"{request.rstrip()}\n{parameter_text}" if request.strip() else parameter_text
    elif parameter_text:
        request = request.replace(parameter_text, "", 1).strip()

    st.session_state["ai_request"] = request


def update_reuse_template_fields():
    selected_templates = [
        template_path
        for template_path in list_markdown_files(PROMPTS_DIR)
        if st.session_state.get(f"reuse_template_{template_path.name}")
    ]
    if not selected_templates:
        st.session_state["new_name"] = ""
        st.session_state["new_content"] = ""
        return

    st.session_state["manage_mode"] = "新規作成"
    st.session_state["new_name"] = (
        selected_templates[0].stem
        if len(selected_templates) == 1
        else "複数テンプレートの流用"
    )
    st.session_state["new_content"] = "\n\n---\n\n".join(
        read_markdown(template_path).rstrip()
        for template_path in selected_templates
    )


def render_gui_customization(current_config):
    if st.session_state.pop("clear_gui_improvement_request", False):
        st.session_state["gui_improvement_request"] = ""

    with st.expander("GUIの改良"):
        with st.form("gui_improvement_form"):
            improvement_request = st.text_area(
                "GUI改善案",
                placeholder="例：対象言語を選択する欄を追加したい",
                max_chars=2000,
                key="gui_improvement_request",
            )
            improve_submitted = st.form_submit_button("改良", type="primary")

        if improve_submitted:
            if not improvement_request.strip():
                st.warning("GUI改善案を入力してください。")
            else:
                try:
                    api_key = st.secrets["GEMINI_API_KEY"]
                    proposed_config = generate_gui_config(
                        api_key,
                        improvement_request,
                        current_config,
                    )
                    save_gui_config(proposed_config)
                    st.session_state["gui_config_notice"] = "GUI設定を更新しました。"
                    st.session_state["clear_gui_improvement_request"] = True
                    st.rerun()
                except Exception as error:
                    st.error("GUI改良に失敗しました。改善案とAPI設定を確認してください。")
                    st.caption(f"エラー詳細：{error}")

        if st.button("GUI設定を初期化", key="reset_gui_config"):
            save_gui_config(DEFAULT_GUI_CONFIG)
            st.session_state["gui_config_notice"] = "GUI設定を初期状態に戻しました。"
            st.rerun()


def render_generation(config):
    st.header(config["generation_heading"])

    generation_type = st.radio(
        "生成するもの",
        ["プロンプト", "ルール", "入力パラメータ"],
        horizontal=True,
        key="generation_type",
    )

    custom_values = render_custom_fields(config)

    st.subheader("流用テンプレート")
    template_files = list_markdown_files(PROMPTS_DIR)
    selected_templates = []
    if not template_files:
        st.caption("流用テンプレートがありません。")
    else:
        template_columns = st.columns(min(3, len(template_files)))
        for index, template_path in enumerate(template_files):
            with template_columns[index % len(template_columns)]:
                if st.checkbox(
                    template_path.stem,
                    key=f"reuse_template_{template_path.name}",
                    on_change=update_reuse_template_fields,
                ):
                    selected_templates.append(template_path)

    st.subheader(config["input_parameters_label"])
    input_parameter_files = list_markdown_files(INPUT_PARAMETERS_DIR)
    if not input_parameter_files:
        st.caption("入力パラメータファイルがありません。")
    else:
        parameter_columns = st.columns(min(3, len(input_parameter_files)))
        for index, parameter_path in enumerate(input_parameter_files):
            with parameter_columns[index % len(parameter_columns)]:
                st.checkbox(
                    parameter_path.stem,
                    key=f"input_parameter_{parameter_path.name}",
                    on_change=update_request_from_input_parameter,
                    args=(
                        parameter_path.name,
                        read_markdown(parameter_path).strip(),
                    ),
                )

    request = st.text_area(
        config["request_label"],
        placeholder=config["request_placeholders"][generation_type],
        height=config["request_height"],
        key="ai_request",
    )

    selected_rules = []
    if generation_type == "プロンプト":
        st.subheader(config["rules_label"])
        rule_files = list_markdown_files(RULES_DIR)
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

    generate_button_label = (
        config["generate_parameter_label"]
        if generation_type == "入力パラメータ"
        else config["generate_prompt_label"]
    )
    if st.button(generate_button_label, type="primary"):
        effective_request = (
            request
            if generation_type == "入力パラメータ"
            else append_custom_values(request, custom_values)
        )
        if not effective_request.strip():
            st.warning("作成したい内容の要望を入力してください。")
        else:
            try:
                if generation_type == "入力パラメータ":
                    generated_text = request
                else:
                    api_key = st.secrets["GEMINI_API_KEY"]
                    with st.spinner("AIが指示文を作成しています..."):
                        generated_text = generate_instruction(
                            generation_type,
                            effective_request,
                            selected_rules,
                            api_key,
                            selected_templates,
                        )

                st.session_state["generated_prompt"] = generated_text
                st.session_state["generated_name"] = "新しい指示文"
                st.session_state["generated_type"] = generation_type
            except Exception as error:
                st.error(
                    "生成に失敗しました。APIキー、モデルの利用可否、"
                    "インターネット接続、利用制限、選択したファイルを確認してください。"
                )
                st.caption(f"エラー詳細：{error}")

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
            else:
                output_directory = {
                    "プロンプト": PROMPTS_DIR,
                    "ルール": RULES_DIR,
                    "入力パラメータ": INPUT_PARAMETERS_DIR,
                }[generated_type]
                try:
                    save_path = save_markdown(
                        output_directory,
                        generated_name,
                        generated_content,
                    )
                    st.success(f"保存しました：{save_path.name}")
                    st.rerun()
                except (ValueError, FileExistsError) as error:
                    st.error(str(error))


def render_prompt_management():
    st.divider()
    st.header("2. 保存済み指示文の管理")

    keyword = st.text_input("検索（ファイル名・本文）").strip().casefold()
    prompt_files = search_prompts(keyword)
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
            else:
                try:
                    save_path = save_markdown(PROMPTS_DIR, name, content)
                    st.success(f"保存しました：{save_path.name}")
                    st.session_state["clear_ai_request"] = True
                    st.rerun()
                except (ValueError, FileExistsError) as error:
                    st.error(str(error))

    elif not prompt_files:
        st.info("該当する指示文がありません。")

    else:
        selected_path = st.selectbox(
            "編集する指示文",
            prompt_files,
            format_func=lambda path: path.stem,
        )
        edited_content = st.text_area(
            "指示文の内容",
            value=read_markdown(selected_path),
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
            overwrite_markdown(selected_path, edited_content)
            st.success(f"保存しました：{selected_path.name}")
            st.rerun()


def render_app():
    config, config_error = load_gui_config()
    st.set_page_config(page_title=config["app_title"], layout="wide")
    initialize_storage()

    if st.session_state.pop("clear_ai_request", False):
        st.session_state["ai_request"] = ""
    if st.session_state.pop("clear_gui_improvement_request", False):
        st.session_state["gui_improvement_request"] = ""

    title_column, update_column = st.columns([8, 1])
    with title_column:
        st.title(config["app_title"])
    with update_column:
        st.button("更新", key="reset_app", on_click=reset_app_state)

    if config_error:
        st.warning("画面設定を読み込めないため、初期設定を使用しています。")
        st.caption(f"設定エラー：{config_error}")
    config_notice = st.session_state.pop("gui_config_notice", None)
    if config_notice:
        st.success(config_notice)

    render_gui_customization(config)
    render_generation(config)
    render_prompt_management()