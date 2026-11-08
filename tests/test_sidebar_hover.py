import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from offline_pdf.workspace import WindowDropHover


class SidebarHoverTests(unittest.TestCase):
    def create(self):
        self.root = Mock()
        self.root.after.return_value = "timer"
        self.native = SimpleNamespace(_drag_active=False)
        self.app = SimpleNamespace(
            root=self.root, host=Mock(), busy=Mock(return_value=False), file_drop=self.native
        )
        with patch("offline_pdf.workspace.tk.Label"), patch("offline_pdf.workspace.tk.Frame"):
            return WindowDropHover(self.app)

    def test_ordinary_pointer_hover_does_not_activate_drop_notice(self):
        hover = self.create()
        hover.poll()
        self.assertFalse(hover.active)
        self.root.winfo_pointerxy.assert_not_called()
        hover.notice.place.assert_not_called()

    def test_only_native_file_drag_shows_whole_window_notice(self):
        hover = self.create()
        self.native._drag_active = True
        hover.poll()
        self.assertTrue(hover.active)
        hover.notice.place.assert_called_once_with(relx=0.5, rely=0.5, anchor="center")
        self.assertTrue(all(edge.place.called for edge in hover.edges))
        self.native._drag_active = False
        hover.poll()
        self.assertFalse(hover.active)
        hover.notice.place_forget.assert_called_once()

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
        self.assertTrue(all(edge.destroy.called for edge in hover.edges))
        self.root.after.reset_mock()
        hover.poll()
        self.root.after.assert_not_called()
