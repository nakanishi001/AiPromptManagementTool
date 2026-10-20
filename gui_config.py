import json
import re
from pathlib import Path

from google import genai

APP_DIR = Path(__file__).parent
GUI_CONFIG_PATH = APP_DIR / "gui_config.json"
MAX_CONFIG_BYTES = 16_384
MAX_CUSTOM_FIELDS = 8
FIELD_TYPES = {"text_input", "text_area", "selectbox", "multiselect", "checkbox"}

DEFAULT_GUI_CONFIG = {
    "app_title": "AIプロンプト作成支援ツール",
    "generation_heading": "1. AIで指示文を作成",
    "request_label": "作成したい内容の要望",
    "request_placeholders": {
        "プロンプト": "例：C言語のソースコードを解析し、全体構造を簡潔に説明させたい。",
        "ルール": "例：周辺のソースコードの書式に合わせるルールを作りたい。",
        "入力パラメータ": "入力パラメータに登録する語句を入力してください。",
    },
    "request_height": 120,
    "input_parameters_label": "入力パラメータ",
    "rules_label": "オプションルール",
    "generate_prompt_label": "AIで指示文を生成",
    "generate_parameter_label": "入力パラメータを作成",
    "custom_fields": [],
}


def _validate_text(value, field_name, max_length=200):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name}には空でない文字列を指定してください。")
    if len(value) > max_length:
        raise ValueError(f"{field_name}は{max_length}文字以内にしてください。")
    return value


def validate_gui_config(config):
    if not isinstance(config, dict):
        raise ValueError("画面設定はJSONオブジェクトである必要があります。")

    expected_keys = set(DEFAULT_GUI_CONFIG)
    if set(config) != expected_keys:
        raise ValueError("画面設定の項目が不足しているか、未対応の項目があります。")

    validated = {
        "app_title": _validate_text(config["app_title"], "app_title", 100),
        "generation_heading": _validate_text(
            config["generation_heading"], "generation_heading", 100
        ),
        "request_label": _validate_text(config["request_label"], "request_label", 100),
        "request_height": config["request_height"],
        "input_parameters_label": _validate_text(
            config["input_parameters_label"], "input_parameters_label", 100
        ),
        "rules_label": _validate_text(config["rules_label"], "rules_label", 100),
        "generate_prompt_label": _validate_text(
            config["generate_prompt_label"], "generate_prompt_label", 100
        ),
        "generate_parameter_label": _validate_text(
            config["generate_parameter_label"], "generate_parameter_label", 100
        ),
    }

    if type(validated["request_height"]) is not int or not 80 <= validated["request_height"] <= 500:
        raise ValueError("request_heightは80から500の整数にしてください。")

    placeholders = config["request_placeholders"]
    placeholder_keys = {"プロンプト", "ルール", "入力パラメータ"}
    if not isinstance(placeholders, dict) or set(placeholders) != placeholder_keys:
        raise ValueError("request_placeholdersの対象が不正です。")
    validated["request_placeholders"] = {
        key: _validate_text(value, f"request_placeholders.{key}", 300)
        for key, value in placeholders.items()
    }

    fields = config["custom_fields"]
    if not isinstance(fields, list) or len(fields) > MAX_CUSTOM_FIELDS:
        raise ValueError(f"custom_fieldsは最大{MAX_CUSTOM_FIELDS}件です。")

    validated_fields = []
    seen_ids = set()
    field_keys = {"id", "label", "type", "options", "placeholder", "help", "include_in_prompt"}
    for field in fields:
        if not isinstance(field, dict) or set(field) != field_keys:
            raise ValueError("入力補助項目の形式が不正です。")

        field_id = field["id"]
        if not isinstance(field_id, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", field_id):
            raise ValueError("入力補助項目のidは英小文字で始まる英数字と_にしてください。")
        if field_id in seen_ids:
            raise ValueError("入力補助項目のidは重複できません。")
        seen_ids.add(field_id)

        field_type = field["type"]
        if not isinstance(field_type, str) or field_type not in FIELD_TYPES:
            raise ValueError("未対応の入力補助項目タイプです。")

        options = field["options"]
        if not isinstance(options, list) or len(options) > 20:
            raise ValueError("入力補助項目のoptionsは最大20件の配列にしてください。")
        if any(not isinstance(option, str) or not option.strip() or len(option) > 100 for option in options):
            raise ValueError("選択肢は1から100文字の文字列にしてください。")
        if len(set(options)) != len(options):
            raise ValueError("選択肢は重複できません。")
        if field_type in {"selectbox", "multiselect"} and not options:
            raise ValueError("選択式の入力補助項目には選択肢が必要です。")
        if field_type not in {"selectbox", "multiselect"} and options:
            raise ValueError("選択式以外の入力補助項目に選択肢は指定できません。")

        for key in ("placeholder", "help"):
            if not isinstance(field[key], str) or len(field[key]) > 200:
                raise ValueError(f"入力補助項目の{key}は200文字以内の文字列にしてください。")
        if type(field["include_in_prompt"]) is not bool:
            raise ValueError("include_in_promptは真偽値にしてください。")

        validated_fields.append(
            {
                "id": field_id,
                "label": _validate_text(field["label"], "入力補助項目のlabel", 100),
                "type": field_type,
                "options": options,
                "placeholder": field["placeholder"],
                "help": field["help"],
                "include_in_prompt": field["include_in_prompt"],
            }
        )

    validated["custom_fields"] = validated_fields
    if len(json.dumps(validated, ensure_ascii=False).encode("utf-8")) > MAX_CONFIG_BYTES:
        raise ValueError("画面設定が許容サイズを超えています。")
    return validated


def load_gui_config(path=GUI_CONFIG_PATH):
    try:
        raw_config = json.loads(Path(path).read_text(encoding="utf-8"))
        return validate_gui_config(raw_config), None
    except FileNotFoundError:
        return validate_gui_config(DEFAULT_GUI_CONFIG), None
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return validate_gui_config(DEFAULT_GUI_CONFIG), str(error)


def save_gui_config(config, path=GUI_CONFIG_PATH):
    validated = validate_gui_config(config)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(
        json.dumps(validated, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return validated


def generate_gui_config(api_key, improvement_request, current_config):
    current = validate_gui_config(current_config)
    prompt = f"""
既存のStreamlitアプリの画面設定JSONを、利用者の改善要望に合わせて改良してください。
PythonコードやMarkdownの説明は出力せず、指定形式のJSONオブジェクトだけを出力してください。

安全上の制約:
- 設定に含められる項目と入力部品は現在のJSON構造にあるものだけです。
- custom_fieldsのtypeはtext_input、text_area、selectbox、multiselect、checkboxのいずれかです。
- idは英小文字で始まる英小文字・数字・アンダースコアで作成してください。
- custom_fieldsは最大8件、選択肢は各20件までです。
- 現行のプロンプト、ルール、入力パラメータ作成の意味や保存処理は変更しないでください。
- 要望が曖昧でも安全な画面設定の変更に限定し、実行コード、URL、ファイルパス、APIキーを追加しないでください。
- include_in_promptがtrueの入力値はプロンプト／ルール生成時の補助情報として利用されます。

JSONの必須構造:
{{
  "app_title": "文字列",
  "generation_heading": "文字列",
  "request_label": "文字列",
  "request_placeholders": {{"プロンプト": "文字列", "ルール": "文字列", "入力パラメータ": "文字列"}},
  "request_height": 120,
  "input_parameters_label": "文字列",
  "rules_label": "文字列",
  "generate_prompt_label": "文字列",
  "generate_parameter_label": "文字列",
  "custom_fields": [{{
    "id": "target_language",
    "label": "対象言語",
    "type": "selectbox",
    "options": ["Python", "TypeScript"],
    "placeholder": "",
    "help": "実装対象の言語",
    "include_in_prompt": true
  }}]
}}

改善要望:
{improvement_request}

現在の設定:
{json.dumps(current, ensure_ascii=False)}
"""
    with genai.Client(api_key=api_key) as client:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
        )
    response_text = (response.text or "").strip()
    if not response_text:
        raise ValueError("AIから画面設定を取得できませんでした。")
    try:
        proposed_config = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise ValueError("AIの応答がJSON形式ではありませんでした。") from error
    return validate_gui_config(proposed_config)