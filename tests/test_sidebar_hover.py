import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from offline_pdf.workspace import WindowDropHover


class SidebarHoverTests(unittest.TestCase):
    def create(self):
        self.root = Mock()
        self.root.after.return_value = "timer"
        self.root.winfo_pointerxy.return_value = (-100, -100)
        self.root.winfo_rootx.return_value = 0
        self.root.winfo_rooty.return_value = 0
        self.root.winfo_width.return_value = 800
        self.root.winfo_height.return_value = 600
        self.native = SimpleNamespace(_drag_active=False)
        self.app = SimpleNamespace(
            root=self.root, host=Mock(), busy=Mock(return_value=False), file_drop=self.native
        )
        with patch("offline_pdf.workspace.tk.Label"):
            return WindowDropHover(self.app)

    def test_ordinary_pointer_hover_does_not_activate_drop_notice(self):
        hover = self.create()
        hover.poll()
        self.assertFalse(hover.active)
        hover._pointer(True)
        self.app.host.configure.assert_called_with(highlightbackground="#3759da")
        self.assertNotIn("highlightthickness", self.app.host.configure.call_args.kwargs)
        self.assertFalse(self.root.bind.called)
        hover.notice.place.assert_not_called()

    def test_only_native_file_drag_shows_whole_window_notice(self):
        hover = self.create()
        self.native._drag_active = True
        hover.poll()
        self.assertTrue(hover.active)
        hover.notice.place.assert_called_once_with(relx=0.5, rely=0.5, anchor="center")
        self.assertNotIn("highlightthickness", self.app.host.configure.call_args.kwargs)
        self.native._drag_active = False
        hover.poll()
        self.assertFalse(hover.active)
        self.assertGreaterEqual(hover.notice.place_forget.call_count, 1)

    def test_busy_disables_visual_drop_target(self):
        hover = self.create()
        self.native._drag_active = True
        self.app.busy.return_value = True
        hover.poll()
        self.assertFalse(hover.active)

    def test_close_stops_polling_and_removes_overlay_widgets(self):
        hover = self.create()
        hover.close()
        self.root.after_cancel.assert_called_once_with("timer")
        hover.notice.destroy.assert_called_once()
        self.root.after.reset_mock()
        hover.poll()
        self.root.after.assert_not_called()
