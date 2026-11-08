import json
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from offline_pdf.app import App
from offline_pdf.appearance import DARK, DEFAULT, apply_theme
from offline_pdf.localization import ChoiceVar, DisplayVar, apply_language, tr
from offline_pdf.preferences import load_preferences, save_preferences
from offline_pdf.settings import show_settings


class PreferencesTests(unittest.TestCase):
    def test_round_trip_only_stores_language_and_theme(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "settings.json"
            with patch("offline_pdf.preferences.preferences_path", return_value=target):
                self.assertEqual(load_preferences(), {"language": "ko", "theme": "default"})
                save_preferences("en", "dark")
                self.assertEqual(load_preferences(), {"language": "en", "theme": "dark"})
                self.assertEqual(set(json.loads(target.read_text())), {"language", "theme"})
                self.assertFalse(target.with_suffix(".tmp").exists())
                with self.assertRaises(ValueError):
                    save_preferences("en", "green")
                target.write_text('{"theme":"green","language":"bad"}')
                self.assertEqual(load_preferences(), {"language": "ko", "theme": "default"})
                target.write_text("broken")
                self.assertEqual(load_preferences(), {"language": "ko", "theme": "default"})


class DisplaySettingsTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest("GUI needs a display")
        self.temp = tempfile.TemporaryDirectory()
        self.target = Path(self.temp.name) / "settings.json"
        self.patcher = patch("offline_pdf.preferences.preferences_path", return_value=self.target)
        self.patcher.start()
        self.app = App(self.root)
        self.root.update()

    def tearDown(self):
        if hasattr(self, "app"):
            apply_theme(self.root, "default")
            apply_language(self.root, "ko")
            self.app.close()
            self.patcher.stop()
            self.temp.cleanup()

    def test_language_changes_display_but_preserves_processing_values_and_inputs(self):
        self.app.select_tool("compress")
        self.app.options["compression"].set("목표 용량")
        self.app.options["target_mb"].set("1.25")
        self.app.output.set("C:/사용자 문서/결과")
        apply_language(self.root, "en")
        self.root.update()
        self.assertEqual(self.app.title.cget("text"), "Compress PDF")
        self.assertEqual(self.app.add_button.cget("text"), "＋  Add files")
        self.assertEqual(self.app.options["compression"].get(), "목표 용량")
        raw = self.root.globalgetvar(str(self.app.options["compression"]))
        self.assertEqual(raw, "Target size")
        self.assertEqual(self.app.options["target_mb"].get(), "1.25")
        self.assertEqual(self.app.output.get(), "C:/사용자 문서/결과")
        self.app.configure_form()
        self.assertEqual(self.app.options["compression"].get(), "권장")
        self.assertEqual(self.app.title.cget("text"), "Compress PDF")
        apply_language(self.root, "ko")
        self.assertEqual(self.app.title.cget("text"), "용량 압축")

    def test_display_variables_and_dynamic_messages_keep_canonical_data(self):
        value = DisplayVar(value="2개 파일 · 0.2 MB")
        choice = ChoiceVar(value="가로", choices=("세로", "가로"))
        apply_language(self.root, "en")
        self.assertEqual(value.get(), "2개 파일 · 0.2 MB")
        self.assertEqual(self.root.globalgetvar(str(value)), "2 files · 0.2 MB")
        self.assertEqual(choice.get(), "가로")
        self.assertEqual(self.root.globalgetvar(str(choice)), "Landscape")
        self.assertEqual(tr("✓  2개 추가 · 전체 3개"), "✓  2 added · Total 3")
        self.assertEqual(tr("페이지 8 OCR"), "OCR page 8")
        self.assertEqual(
            tr("생성할 파일  1: 1–3쪽  /  2: 4–6쪽"),
            "Output files  1: pages 1–3  /  2: pages 4–6",
        )
        self.assertNotIn("쪽", tr("페이지는 1~8 범위여야 합니다."))
        self.assertEqual(tr("고객자료_비공개.pdf"), "고객자료_비공개.pdf")

    def test_full_theme_round_trip_and_card_legibility(self):
        apply_theme(self.root, "dark")
        for card in self.app.cards.values():
            card.paint()
            self.assertEqual(card.cget("bg"), DARK["BG"])
        self.assertEqual(self.app.sidebar.cget("bg"), DARK["PANEL"])
        style = tk.ttk.Style(self.root)
        self.assertEqual(style.lookup("TEntry", "fieldbackground"), DARK["PANEL"])
        apply_theme(self.root, "default")
        self.assertEqual(self.app.sidebar.cget("bg"), DEFAULT["PANEL"])
        self.assertEqual(style.lookup("TEntry", "fieldbackground"), DEFAULT["PANEL"])

    def test_settings_dialog_offers_only_two_themes_and_saves(self):
        dialog = show_settings(self.app)
        self.root.update()
        radios = []
        buttons = []

        def visit(w):
            if isinstance(w, tk.ttk.Radiobutton):
                radios.append(w)
            if isinstance(w, tk.ttk.Button):
                buttons.append(w)
            for c in w.winfo_children():
                visit(c)

        visit(dialog)
        self.assertEqual({w.cget("value") for w in radios}, {"ko", "en", "default", "dark"})
        for radio in radios:
            if radio.cget("value") in ("en", "dark"):
                radio.invoke()
        next(w for w in buttons if w.cget("text") == "적용").invoke()
        self.root.update()
        self.assertEqual(load_preferences(), {"language": "en", "theme": "dark"})
        self.assertEqual(self.app.settings_button.cget("text"), "Settings")
        self.assertEqual(self.app.home_title.cget("text"), "Choose a tool")

    def test_english_tool_forms_and_options_open_without_korean_labels(self):
        apply_language(self.root, "en")
        for tool in self.app.cards:
            self.app.tool = tool
            self.app.configure_form()
            self.root.update()
            self.assertFalse(any("가" <= c <= "힣" for c in self.app.title.cget("text")), tool)
            for child in self.app.form.winfo_children():
                for label in child.winfo_children():
                    if isinstance(label, tk.ttk.Label):
                        self.assertFalse(
                            any("가" <= c <= "힣" for c in label.cget("text")),
                            (tool, label.cget("text")),
                        )
