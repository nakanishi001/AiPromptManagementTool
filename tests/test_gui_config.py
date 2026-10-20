import copy
from contextlib import ExitStack
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import app_view
import gui_config
import prompt_service


APP_ROOT = Path(__file__).resolve().parents[1]


class GuiConfigTests(unittest.TestCase):
    def test_default_config_passes_schema_validation(self):
        self.assertEqual(
            gui_config.validate_gui_config(gui_config.DEFAULT_GUI_CONFIG),
            gui_config.DEFAULT_GUI_CONFIG,
        )

    def test_schema_rejects_unapproved_widget_type(self):
        config = copy.deepcopy(gui_config.DEFAULT_GUI_CONFIG)
        config["custom_fields"] = [
            {
                "id": "unsafe_field",
                "label": "項目",
                "type": "python",
                "options": [],
                "placeholder": "",
                "help": "",
                "include_in_prompt": True,
            }
        ]

        with self.assertRaises(ValueError):
            gui_config.validate_gui_config(config)

    def test_config_is_saved_and_loaded_as_validated_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            config_path = Path(temporary_directory) / "gui_config.json"
            saved = gui_config.save_gui_config(
                gui_config.DEFAULT_GUI_CONFIG,
                config_path,
            )
            loaded, error = gui_config.load_gui_config(config_path)

        self.assertIsNone(error)
        self.assertEqual(loaded, saved)

    def test_ai_response_is_parsed_and_validated(self):
        response_text = json.dumps(gui_config.DEFAULT_GUI_CONFIG, ensure_ascii=False)
        with patch("gui_config.genai.Client") as client_factory:
            client = client_factory.return_value.__enter__.return_value
            client.models.generate_content.return_value.text = response_text
            result = gui_config.generate_gui_config(
                "test-key",
                "入力欄を整える",
                gui_config.DEFAULT_GUI_CONFIG,
            )

        self.assertEqual(result, gui_config.DEFAULT_GUI_CONFIG)

    def test_generation_request_includes_selected_template_and_new_request(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            template_path = Path(temporary_directory) / "base.md"
            template_path.write_text("Keep API backward compatible", encoding="utf-8")
            with patch("prompt_service.genai.Client") as client_factory:
                client = client_factory.return_value.__enter__.return_value
                client.models.generate_content.return_value.text = "generated prompt"
                result = prompt_service.generate_instruction(
                    "プロンプト",
                    "add a migration section",
                    [],
                    "test-key",
                    [template_path],
                )

        sent_request = client.models.generate_content.call_args.kwargs["contents"]
        self.assertIn("Keep API backward compatible", sent_request)
        self.assertIn("add a migration section", sent_request)
        self.assertEqual(result, "generated prompt")

    def test_selecting_template_populates_management_fields(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            directories = {
                "prompts": root / "prompts",
                "rules": root / "rules",
                "input_parameters": root / "input_parameters",
            }
            for directory in directories.values():
                directory.mkdir()
            (directories["prompts"] / "base.md").write_text(
                "Reusable instruction body",
                encoding="utf-8",
            )
            (directories["prompts"] / "addendum.md").write_text(
                "Additional template guidance",
                encoding="utf-8",
            )

            with ExitStack() as stack:
                for module in (prompt_service, app_view):
                    for directory_name, directory in directories.items():
                        stack.enter_context(
                            patch.object(module, f"{directory_name.upper()}_DIR", directory)
                        )

                app = AppTest.from_file(str(APP_ROOT / "app.py")).run()
                app.radio(key="manage_mode").set_value("既存の指示文を編集").run()
                app.checkbox(key="reuse_template_base.md").check().run()

                self.assertFalse(app.exception)
                self.assertEqual(app.radio(key="manage_mode").value, "新規作成")
                self.assertEqual(app.text_input(key="new_name").value, "base")
                self.assertEqual(
                    app.text_area(key="new_content").value,
                    "Reusable instruction body",
                )

                app.checkbox(key="reuse_template_addendum.md").check().run()
                self.assertEqual(
                    app.text_input(key="new_name").value,
                    "複数テンプレートの流用",
                )
                self.assertEqual(
                    app.text_area(key="new_content").value,
                    "Additional template guidance\n\n---\n\nReusable instruction body",
                )

    def test_selected_template_is_passed_to_prompt_generation(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            directories = {
                "prompts": root / "prompts",
                "rules": root / "rules",
                "input_parameters": root / "input_parameters",
            }
            for directory in directories.values():
                directory.mkdir()
            template_path = directories["prompts"] / "base.md"
            template_path.write_text("Reusable template", encoding="utf-8")

            with ExitStack() as stack:
                for module in (prompt_service, app_view):
                    for directory_name, directory in directories.items():
                        stack.enter_context(
                            patch.object(module, f"{directory_name.upper()}_DIR", directory)
                        )
                stack.enter_context(
                    patch.object(app_view.st, "secrets", {"GEMINI_API_KEY": "test-key"})
                )
                generate_instruction = stack.enter_context(
                    patch.object(
                        app_view,
                        "generate_instruction",
                        return_value="generated prompt",
                    )
                )

                app = AppTest.from_file(str(APP_ROOT / "app.py")).run()
                app.checkbox(key="reuse_template_base.md").check().run()
                app.text_area(key="ai_request").set_value("Add a migration section")
                next(
                    button
                    for button in app.button
                    if button.label == "AIで指示文を生成"
                ).click().run()

                self.assertFalse(app.exception)
                self.assertEqual(
                    generate_instruction.call_args.args[1],
                    "Add a migration section",
                )
                self.assertEqual(
                    generate_instruction.call_args.args[4],
                    [template_path],
                )

    def test_gui_improvement_updates_config_and_renders_custom_field(self):
        current_config = copy.deepcopy(gui_config.DEFAULT_GUI_CONFIG)
        proposed_config = copy.deepcopy(current_config)
        proposed_config["app_title"] = "改良後タイトル"
        proposed_config["custom_fields"] = [
            {
                "id": "target_language",
                "label": "対象言語",
                "type": "selectbox",
                "options": ["Python", "TypeScript"],
                "placeholder": "",
                "help": "実装対象の言語",
                "include_in_prompt": True,
            }
        ]
        saved_config = {"value": current_config}

        def load_config():
            return saved_config["value"], None

        def save_config(config):
            saved_config["value"] = config
            return config

        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            directories = {
                "prompts": root / "prompts",
                "rules": root / "rules",
                "input_parameters": root / "input_parameters",
            }
            for directory in directories.values():
                directory.mkdir()

            with ExitStack() as stack:
                stack.enter_context(
                    patch.object(app_view, "load_gui_config", side_effect=load_config)
                )
                stack.enter_context(
                    patch.object(app_view, "save_gui_config", side_effect=save_config)
                )
                generate_config = stack.enter_context(
                    patch.object(
                        app_view,
                        "generate_gui_config",
                        return_value=proposed_config,
                    )
                )
                stack.enter_context(
                    patch.object(
                        app_view.st,
                        "secrets",
                        {"GEMINI_API_KEY": "test-key"},
                    )
                )
                for module in (prompt_service, app_view):
                    for directory_name, directory in directories.items():
                        stack.enter_context(
                            patch.object(module, f"{directory_name.upper()}_DIR", directory)
                        )

                app = AppTest.from_file(str(APP_ROOT / "app.py")).run()
                self.assertFalse(app.exception)

                app.text_area(key="gui_improvement_request").set_value(
                    "対象言語の選択欄を追加する"
                )
                app.form_submit_button[0].click().run()

                self.assertFalse(app.exception)
                generate_config.assert_called_once()
                self.assertEqual(app.title[0].value, "改良後タイトル")
                self.assertEqual(
                    app.selectbox(key="ui_field_target_language_selectbox").value,
                    "Python",
                )
                self.assertTrue(app.success)
                self.assertEqual(saved_config["value"], proposed_config)

                next(
                    button
                    for button in app.button
                    if button.label == "GUI設定を初期化"
                ).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(
                    saved_config["value"],
                    gui_config.DEFAULT_GUI_CONFIG,
                )
                self.assertEqual(app.title[0].value, "AIプロンプト作成支援ツール")


if __name__ == "__main__":
    unittest.main()