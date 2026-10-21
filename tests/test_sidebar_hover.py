import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from offline_pdf.workspace import WindowDropHover


def rectangle(x, y, width, height):
    widget = Mock()
    widget.winfo_ismapped.return_value = True
    widget.winfo_rootx.return_value = x
    widget.winfo_rooty.return_value = y
    widget.winfo_width.return_value = width
    widget.winfo_height.return_value = height
    return widget


class SidebarHoverTests(unittest.TestCase):
    def setUp(self):
        self.app = SimpleNamespace(
            root=Mock(),
            host=rectangle(0, 50, 1000, 600),
            sidebar=rectangle(0, 50, 224, 600),
            add_button=Mock(),
            file_count=Mock(),
            file_list=Mock(),
            busy=Mock(return_value=False),
        )
        self.app.root.winfo_pointerxy.return_value = (100, 200)
        self.app.root.winfo_containing.return_value = None
        self.app.add_button.cget.return_value = "＋  파일 추가"

    def create(self):
        with patch("offline_pdf.workspace.Tween"):
            return WindowDropHover(self.app)

    def test_external_drag_without_tk_hit_still_highlights_sidebar(self):
        hover = self.create()
        self.assertTrue(hover.active)
        self.assertTrue(hover.sidebar_active)
        hover.sidebar_tween.to.assert_called_with(1)
        self.app.root.winfo_containing.assert_not_called()
        self.assertIn("여기에 놓아", self.app.add_button.configure.call_args.kwargs["text"])
        hover.paint_sidebar(1)
        self.assertEqual(self.app.file_list.drop_hover, 1)
        self.app.file_list.itemconfigure.assert_called_once()

    def test_leave_busy_and_minimized_restore_normal_state(self):
        hover = self.create()
        self.app.root.winfo_pointerxy.return_value = (500, 200)
        hover.poll()
        self.assertFalse(hover.sidebar_active)
        self.assertTrue(hover.active)
        self.app.root.winfo_pointerxy.return_value = (100, 200)
        self.app.busy.return_value = True
        hover.poll()
        self.assertFalse(hover.active)
        self.app.busy.return_value = False
        self.app.host.winfo_ismapped.return_value = False
        hover.poll()
        self.assertFalse(hover.sidebar_active)
        self.app.add_button.configure.assert_called_with(text="＋  파일 추가")

    def test_negative_monitor_coordinates_and_window_move(self):
        self.app.host = rectangle(-1600, -800, 1000, 600)
        self.app.sidebar = rectangle(-1600, -800, 224, 600)
        self.app.root.winfo_pointerxy.return_value = (-1500, -600)
        hover = self.create()
        self.assertTrue(hover.sidebar_active)
        self.app.sidebar.winfo_rootx.return_value = -1100
        hover.poll()
        self.assertFalse(hover.sidebar_active)

    def test_transient_tk_error_reschedules_and_close_stops_polling(self):
        self.app.root.winfo_pointerxy.side_effect = tk.TclError("screen changing")
        hover = self.create()
        self.app.root.after.assert_called_with(70, hover.poll)
        self.app.root.winfo_pointerxy.side_effect = None
        hover.poll()
        self.assertTrue(hover.sidebar_active)
        hover.close()
        self.app.root.after.reset_mock()
        hover.poll()
        self.app.root.after.assert_not_called()
