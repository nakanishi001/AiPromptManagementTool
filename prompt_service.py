from pathlib import Path

from google import genai

APP_DIR = Path(__file__).parent
PROMPTS_DIR = APP_DIR / "prompts"
RULES_DIR = APP_DIR / "rules"
INPUT_PARAMETERS_DIR = APP_DIR / "input_parameters"


def initialize_storage():
    for directory in (PROMPTS_DIR, RULES_DIR, INPUT_PARAMETERS_DIR):
        directory.mkdir(exist_ok=True)


def valid_filename(name):
    return (
        bool(name.strip())
        and Path(name).name == name
        and name not in {".", ".."}
        and not any(character in name for character in '/\\:\x00')
    )


def list_markdown_files(directory):
    return sorted(Path(directory).glob("*.md"))


def search_prompts(keyword):
    prompt_files = list_markdown_files(PROMPTS_DIR)
    if not keyword:
        return prompt_files

    normalized_keyword = keyword.strip().casefold()
    return [
        path
        for path in prompt_files
        if normalized_keyword in path.stem.casefold()
        or normalized_keyword in path.read_text(encoding="utf-8").casefold()
    ]


def read_markdown(path):
    return Path(path).read_text(encoding="utf-8")


def save_markdown(directory, name, content):
    if not valid_filename(name):
        raise ValueError("ファイル名を正しく入力してください。")
    if not content.strip():
        raise ValueError("内容を入力してください。")

    save_path = Path(directory) / f"{name.strip()}.md"
    if save_path.exists():
        raise FileExistsError("同じ名前のファイルが存在します。")

    save_path.write_text(content, encoding="utf-8")
    return save_path


def overwrite_markdown(path, content):
    Path(path).write_text(content, encoding="utf-8")


def generate_instruction(
    generation_type,
    request,
    selected_rules,
    api_key,
    selected_templates=(),
):
    if generation_type == "プロンプト":
        selected_rule_text = "\n\n".join(
            f"### {rule_path.stem}\n{read_markdown(rule_path)}"
            for rule_path in selected_rules
        ) or "（指定なし）"
        selected_template_text = "\n\n".join(
            f"### {template_path.stem}\n{read_markdown(template_path)}"
            for template_path in selected_templates
        ) or "（指定なし）"
        instruction = f"""
あなたは、AIへの指示文を設計するアシスタントです。
ユーザーの要望を実現するための指示文を日本語で作成してください。

条件：
- そのままAIに入力して使える指示文にする
- 必要な作業内容、出力形式、注意事項を整理する
- 不明な条件を勝手に事実として決めつけない
- Markdown形式で出力する
- 指示文そのものだけを出力し、前置きや解説は付けない
- 流用テンプレートがある場合は土台として活用し、今回の要望を反映して重複や矛盾を整理する

適用するオプションルール：
{selected_rule_text}

流用テンプレート：
{selected_template_text}

ユーザーの要望：
{request}
"""
    elif generation_type == "ルール":
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
    else:
        raise ValueError("AI生成対象が不正です。")

    with genai.Client(api_key=api_key) as client:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=instruction,
        )
    if not response.text:
        raise ValueError("AIから文章を取得できませんでした。")
    return response.text