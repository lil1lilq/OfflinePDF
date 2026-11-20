"""Owner placement, nested dialogs, and native Windows activation positioning."""

import sys
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import customtkinter as ctk

from offline_pdf import dialogs
from offline_pdf.app import App


class DialogPositionTests(unittest.TestCase):
    def test_centers_on_right_left_and_upper_monitors_and_clamps_to_work_area(self):
        cases = [
            ((2100, 100, 3100, 900), (400, 200), (1920, 0, 3840, 1040), (2400, 400)),
            ((-1900, 100, -900, 900), (500, 400), (-1920, 0, 0, 1040), (-1650, 300)),
            ((100, -1000, 1000, -300), (500, 400), (0, -1080, 1920, 0), (300, -850)),
            ((-2400, -1000, -1500, -500), (500, 300), (-1920, -1080, 0, 0), (-1920, -900)),
            ((1700, 900, 2100, 1200), (500, 300), (0, 0, 1920, 1040), (1420, 740)),
        ]
        for owner, size, bounds, expected in cases:
            with self.subTest(owner=owner):
                self.assertEqual(dialogs.center_position(owner, size, bounds), expected)

    def test_custom_window_preserves_absolute_negative_coordinates(self):
        dialog = Mock(spec=ctk.CTkToplevel)
        dialog.winfo_width.return_value = 500
        dialog.winfo_height.return_value = 400
        dialog.winfo_reqwidth.return_value = 500
        dialog.winfo_reqheight.return_value = 400
        owner = SimpleNamespace(
            winfo_rootx=lambda: -1900,
            winfo_rooty=lambda: 100,
            winfo_width=lambda: 1000,
            winfo_height=lambda: 800,
        )
        with patch.object(dialogs, "monitor_work_area", return_value=(-1920, 0, 0, 1040)):
            dialogs.place_dialog(dialog, owner)
        dialog.geometry.assert_called_once_with("+-1650+300")
        dialog.transient.assert_called_once_with(owner)
        dialog.deiconify.assert_called_once()

    def test_native_picker_uses_active_modal_and_releases_position_hook_on_failure(self):
        parent, modal = object(), object()
        with (
            patch.object(dialogs, "dialog_parent", return_value=modal),
            patch.object(dialogs, "native_dialog_position") as positioning,
            patch("tkinter.filedialog.askdirectory", return_value="D:/PDF") as operation,
        ):
            self.assertEqual(dialogs.filedialog.askdirectory(parent=parent, title="PDF"), "D:/PDF")
            operation.assert_called_once_with(parent=modal, title="PDF")
            positioning.assert_called_once_with(modal)
            positioning.return_value.__exit__.assert_called_once()
        with (
            patch.object(dialogs, "dialog_parent", return_value=modal),
            patch.object(dialogs, "native_dialog_position") as positioning,
            patch("tkinter.messagebox.showinfo", side_effect=OSError("dialog failed")),
        ):
            with self.assertRaises(OSError):
                dialogs.messagebox.showinfo("Title", "Message", parent=parent)
            positioning.return_value.__exit__.assert_called_once()


class DialogGuiTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = ctk.CTk()
        except tk.TclError:
            self.skipTest("GUI requires a display")
        self.app = App(self.root)
        self.root.geometry("1100x800+120+80")
        self.root.update()

    def tearDown(self):
        if hasattr(self, "app"):
            self.app.close()

    def assert_centered(self, dialog):
        self.root.update()
        owner = dialogs.widget_rect(self.root)
        bounds = dialogs.monitor_work_area(owner) or owner
        expected = dialogs.center_position(
            owner, (dialog.winfo_width(), dialog.winfo_height()), bounds
        )
        # Windows window chrome can offset the Tk client origin from wm geometry.
        self.assertAlmostEqual(dialog.winfo_rootx(), expected[0], delta=16)
        self.assertAlmostEqual(dialog.winfo_rooty(), expected[1], delta=40)

    def test_settings_about_updates_and_organizer_dialogs_follow_owner(self):
        from offline_pdf.about import show_about
        from offline_pdf.settings import show_settings
        from offline_pdf.updates import UpdateDialog

        for factory in (show_settings, show_about, lambda app: app.organizer_settings()):
            with self.subTest(factory=factory):
                dialog = factory(self.app)
                self.assert_centered(dialog)
                dialog.destroy()
        with patch.object(UpdateDialog, "launch"):
            updater = UpdateDialog(self.app)
            try:
                self.assert_centered(updater.dialog)
            finally:
                updater.close()

    def test_nested_text_prompt_keeps_settings_owner_and_restores_its_grab(self):
        settings = self.app.organizer_settings()
        self.root.update()
        self.assertIs(dialogs.dialog_parent(self.root), settings)
        observations = []

        def answer():
            dialog = self.root.grab_current()
            observations.append(dialog.master)
            buttons = dialog.winfo_children()[0].winfo_children()[-1].winfo_children()
            # Enter the page plan in the only editable field.
            entry = next(
                w
                for w in dialog.winfo_children()[0].winfo_children()
                if isinstance(w, ctk.CTkEntry)
            )
            entry.insert(0, "3,1,2")
            next(w for w in buttons if w.source_text == "확인").invoke()

        self.root.after(100, answer)
        self.assertEqual(dialogs.ask_text(self.root, "페이지 번호로 지정", "1-3"), "3,1,2")
        self.assertEqual(observations, [settings])
        self.assertIs(self.root.grab_current(), settings)
        settings.destroy()

    def test_password_prompt_belongs_to_current_settings_dialog(self):
        from offline_pdf.passwords import ask_password

        settings = self.app.organizer_settings()
        self.root.update()
        observations = []

        def cancel():
            dialog = self.root.grab_current()
            observations.append(dialog.master)
            actions = dialog.winfo_children()[0].winfo_children()[-1]
            next(
                button for button in actions.winfo_children() if button.source_text == "취소"
            ).invoke()

        self.root.after(100, cancel)
        self.assertIsNone(ask_password(self.app, output=True))
        self.assertEqual(observations, [settings])
        self.assertIs(self.root.grab_current(), settings)
        settings.destroy()

    @unittest.skipUnless(sys.platform == "win32", "Windows native window hooks required")
    def test_native_dialog_is_centered_when_activated(self):
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        create = user32.CreateWindowExW
        create.argtypes = [
            wintypes.DWORD,
            wintypes.LPCWSTR,
            wintypes.LPCWSTR,
            wintypes.DWORD,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.HWND,
            wintypes.HMENU,
            wintypes.HINSTANCE,
            wintypes.LPVOID,
        ]
        create.restype = wintypes.HWND
        destroy = user32.DestroyWindow
        destroy.argtypes = [wintypes.HWND]
        show = user32.ShowWindow
        show.argtypes = [wintypes.HWND, ctypes.c_int]
        activate = user32.SetActiveWindow
        activate.argtypes = [wintypes.HWND]
        activate.restype = wintypes.HWND
        window = None
        with dialogs.native_dialog_position(self.root):
            owner = user32.GetAncestor(self.root.winfo_id(), 2)
            try:
                window = create(
                    0,
                    "#32770",
                    "OfflinePDF dialog test",
                    0x80C80000,
                    0,
                    0,
                    360,
                    180,
                    owner,
                    None,
                    None,
                    None,
                )
                self.assertTrue(window)
                show(window, 1)
                activate(window)
                actual, parent = wintypes.RECT(), wintypes.RECT()
                self.assertTrue(user32.GetWindowRect(window, ctypes.byref(actual)))
                self.assertTrue(user32.GetWindowRect(owner, ctypes.byref(parent)))
                anchor = parent.left, parent.top, parent.right, parent.bottom
                bounds = dialogs.monitor_work_area(anchor) or anchor
                expected = dialogs.center_position(
                    anchor, (actual.right - actual.left, actual.bottom - actual.top), bounds
                )
                self.assertEqual((actual.left, actual.top), expected)
            finally:
                if window:
                    destroy(window)
