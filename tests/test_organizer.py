import unittest

from offline_pdf.engine import UserError
from offline_pdf.organizer import PageOrder


class PageOrderTests(unittest.TestCase):
    def test_segments_survive_moving_and_deleting_boundary_pages(self):
        m = PageOrder(6)
        m.set_cuts({2, 4})
        m.move({2}, 4)
        self.assertEqual(
            [[p["page"] for p in group] for group in m.segments()], [[0], [2, 3], [1, 4, 5]]
        )
        m.selected = {3, 4}
        m.delete()
        self.assertEqual([[p["page"] for p in group] for group in m.segments()], [[0], [1, 4, 5]])
        m.undo()
        self.assertEqual([len(group) for group in m.segments()], [1, 2, 3])
        m.undo()
        self.assertEqual([len(group) for group in m.segments()], [2, 2, 2])
        m.undo()
        self.assertEqual(m.cuts(), set())

    def test_move_across_boundary_can_change_file_without_changing_order(self):
        m = PageOrder(4)
        m.set_cuts({2})
        self.assertTrue(m.move({2}, 2))
        self.assertEqual([p[1] for p in m.items], [0, 1, 2, 3])
        self.assertEqual([len(group) for group in m.segments()], [1, 3])
        m.undo()
        self.assertEqual(m.cuts(), {2})

    def test_dragging_entire_document_does_not_merge_output_files(self):
        m = PageOrder(4)
        m.set_cuts({2})
        self.assertFalse(m.move({1, 2, 3, 4}, 4))
        self.assertEqual(m.cuts(), {2})

    def test_cut_validation_and_rotation_share_undo_history(self):
        m = PageOrder(4)
        for cut in (0, 4, -1, True, 1.5):
            with self.assertRaises(UserError):
                m.set_cuts({cut})
        m.toggle_cut(2)
        m.selected = {3}
        m.rotate()
        m.undo()
        self.assertEqual(m.cuts(), {2})
        m.undo()
        self.assertEqual(m.cuts(), set())

    def test_move_selected_group_and_undo(self):
        m = PageOrder(6)
        m.selected = {2, 4}
        self.assertTrue(m.move(m.selected, 6))
        self.assertEqual([p[1] for p in m.items], [0, 2, 4, 5, 1, 3])
        m.undo()
        self.assertEqual([p[1] for p in m.items], list(range(6)))
        self.assertEqual(m.selected, {2, 4})

    def test_noop_move_does_not_add_history(self):
        m = PageOrder(4)
        self.assertFalse(m.move({2}, 2))
        self.assertEqual(m.history, [])

    def test_delete_rotate_reset_and_undo(self):
        m = PageOrder(4)
        m.selected = {1, 3}
        m.rotate()
        m.delete()
        self.assertEqual([p[1] for p in m.items], [1, 3])
        m.undo()
        self.assertEqual([p["rotation"] for p in m.plan()], [90, 0, 90, 0])
        m.reset()
        self.assertEqual([p["rotation"] for p in m.plan()], [0] * 4)
        m.undo()
        self.assertEqual([p["rotation"] for p in m.plan()], [90, 0, 90, 0])

    def test_refuse_delete_all(self):
        m = PageOrder(2)
        m.selected = {1, 2}
        with self.assertRaises(UserError):
            m.delete()
        self.assertEqual(len(m.items), 2)
        self.assertEqual(m.history, [])

    def test_numeric_order_allows_independent_duplicates(self):
        m = PageOrder(3)
        m.apply_text("3,1,1")
        m.selected = {m.items[1][0]}
        m.rotate()
        self.assertEqual(
            m.plan(),
            [{"page": 2, "rotation": 0}, {"page": 0, "rotation": 90}, {"page": 0, "rotation": 0}],
        )
