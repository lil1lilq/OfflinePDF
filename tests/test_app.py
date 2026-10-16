import os
import ctypes
import struct
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import pymupdf as pdf
from offline_pdf.app import App, TOOLS


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:cls.root=tk.Tk()
        except tk.TclError:raise unittest.SkipTest('GUI requires an available Windows desktop or X display.')
        cls.app=App(cls.root);cls.app.auto_open.set(False);cls.root.update()
        cls.temp=tempfile.TemporaryDirectory();cls.folder=Path(cls.temp.name)
        cls.source=cls.folder/'한글 파일.pdf'
        with pdf.open() as doc:
            for text in ('FIRST','SECOND'):
                p=doc.new_page();p.insert_text((72,72),text)
            doc.save(cls.source)

    @classmethod
    def tearDownClass(cls):
        cls.app.close();cls.temp.cleanup()

    def test_a_all_tool_forms_open(self):
        for tool in TOOLS:
            self.app.tool=tool;self.app.configure_form();self.root.update()
            self.assertIn('input_password',self.app.options)
            self.assertEqual(self.app.title.cget('text'),TOOLS[tool][0])

    def test_b_preview_and_page_navigation(self):
        self.app.tool='rotate';self.app.configure_form();self.app.files=[str(self.source)];self.app.sync_list()
        self.app.refresh_preview(reset=True);self.root.update()
        self.assertIsNotNone(self.app.preview_rect);self.assertEqual(self.app.page_index,0)
        self.app.turn(1);self.assertEqual(self.app.page_index,1)
        self.app.turn(1);self.assertEqual(self.app.page_index,1)

    def test_c_complete_gui_job(self):
        self.app.tool='rotate';self.app.configure_form();self.app.files=[str(self.source)];self.app.sync_list()
        self.app.options['pages'].set('1');self.app.options['angle'].set('90');self.app.output.set(str(self.folder))
        with patch('offline_pdf.app.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')):
            self.app.run();deadline=time.monotonic()+20
            while self.app.process is not None and time.monotonic()<deadline:
                self.root.update();time.sleep(.02)
        self.assertIsNone(self.app.process);self.assertIsNotNone(self.app.result_folder)
        with pdf.open(next(Path(self.app.result_folder).glob('*.pdf'))) as doc:
            self.assertEqual(doc[0].rotation,90);self.assertEqual(doc[1].rotation,0)

    def test_d_drop_multiple_unicode_files_and_deduplicate(self):
        second=self.folder/'공백 {있는} 두 번째.PDF';second.write_bytes(self.source.read_bytes())
        self.app.tool='merge';self.app.configure_form();self.app.clear_files()
        self.app.on_files_drop([str(self.source),str(second),str(self.source)])
        self.assertEqual(self.app.files,[str(self.source.resolve()),str(second.resolve())])
        self.assertIn('중복 1개',self.app.status.get())
        self.assertIsNotNone(self.app.preview_rect)

    def test_e_drop_unsupported_files_folder_and_cloud(self):
        blocked=self.folder/'OneDrive'/'private.pdf';blocked.parent.mkdir(exist_ok=True);blocked.write_bytes(self.source.read_bytes())
        self.app.tool='merge';self.app.configure_form();self.app.clear_files()
        self.app.on_files_drop([str(self.folder),str(self.folder/'unknown.txt'),str(blocked),str(self.source)])
        self.assertEqual(self.app.files,[str(self.source.resolve())])
        self.assertIn('지원하지 않는 항목 2개',self.app.status.get());self.assertIn('경로 1개 제외',self.app.status.get())

    def test_f_drop_image_for_image_tool(self):
        image=self.folder/'사진 한 장.png'
        with pdf.open(self.source) as source:source[0].get_pixmap().save(image)
        self.app.tool='images_pdf';self.app.configure_form();self.app.clear_files()
        self.app.on_files_drop([str(image),str(self.source)])
        self.assertEqual(self.app.files,[str(image.resolve())])
        self.assertIn('JPG·PNG',self.app.status.get())

    def test_g_drop_while_busy(self):
        self.app.tool='merge';self.app.configure_form();self.app.clear_files()
        with patch.object(self.app,'busy',return_value=True):self.app.on_files_drop([str(self.source)])
        self.assertFalse(self.app.files);self.assertIn('작업 중에는',self.app.status.get())

    def test_i_card_home_expand_and_task_navigation(self):
        self.app.show_home();self.root.update()
        self.assertTrue(self.app.home.winfo_ismapped())
        self.assertEqual(sum(card.winfo_ismapped() for card in self.app.cards.values()),6)
        self.app.all_tools_button.invoke();self.root.update()
        self.assertEqual(sum(card.winfo_ismapped() for card in self.app.cards.values()),18)
        sizes={(card.winfo_width(),card.winfo_height()) for card in self.app.cards.values()}
        # One-pixel rounding across equal grid columns is normal.
        self.assertLessEqual(max(w for w,h in sizes)-min(w for w,h in sizes),1)
        self.assertEqual({h for w,h in sizes},{168})
        self.app.select_tool('redact');self.root.update()
        self.assertTrue(self.app.work.winfo_ismapped());self.assertFalse(self.app.home.winfo_ismapped())
        self.assertTrue(self.app.region_controls.winfo_ismapped())
        with patch.object(self.app,'busy',return_value=True):
            self.app.show_home();self.app.select_tool('merge')
        self.assertEqual(self.app.tool,'redact');self.assertTrue(self.app.work.winfo_ismapped())
        self.app.back_button.invoke();self.root.update();self.assertTrue(self.app.home.winfo_ismapped())
        self.app.all_tools_button.invoke();self.root.update()
        self.assertEqual(sum(card.winfo_ismapped() for card in self.app.cards.values()),6)

    def test_j_switch_image_category_clears_incompatible_files(self):
        self.app.select_tool('merge');self.app.files=[str(self.source)];self.app.sync_list()
        self.app.select_tool('rotate');self.assertEqual(self.app.files,[str(self.source)])
        self.app.select_tool('images_pdf');self.assertEqual(self.app.files,[])
        self.assertEqual(str(self.app.run_button.cget('state')),'disabled')

    def test_k_gui_merge_name_and_auto_open(self):
        self.app.select_tool('merge');self.app.files=[str(self.source)];self.app.sync_list()
        self.app.output_name.set('최종 합친문서.pdf');self.app.auto_open.set(True)
        with patch.object(self.app,'open_result') as opened,patch('offline_pdf.app.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')):
            self.app.run();deadline=time.monotonic()+20
            self.assertEqual(str(self.app.back_button.cget('state')),'disabled')
            while self.app.process is not None and time.monotonic()<deadline:
                self.root.update();time.sleep(.02)
            self.assertIsNone(self.app.process)
            opened.assert_called_once()
        self.app.auto_open.set(False)
        self.assertTrue((Path(self.app.result_folder)/'최종 합친문서.pdf').is_file())
        self.assertEqual(str(self.app.back_button.cget('state')),'normal')

    def test_l_responsive_card_grid_and_scrolling(self):
        self.app.show_home();self.app.toggle_tools();self.root.geometry('900x650');self.root.update()
        self.assertEqual(self.app.card_columns,2)
        self.assertEqual(len(self.app.cards_frame.grid_slaves()),18)
        self.app.home.canvas.yview_moveto(1);self.root.update()
        self.assertGreater(self.app.home.canvas.yview()[0],0)
        self.app.toggle_tools();self.root.geometry('1180x850');self.root.update()

    def test_m_preview_and_always_visible_run_button(self):
        self.root.geometry('900x650');self.app.select_tool('merge');self.root.update()
        self.assertFalse(self.app.preview_panel.winfo_ismapped())
        self.app.preview_button.invoke();self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.app.select_tool('redact');self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertEqual(str(self.app.preview_button.cget('state')),'disabled')
        button=self.app.run_button
        self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.root.winfo_rooty()+self.root.winfo_height())
        self.app.select_tool('merge');self.root.geometry('1180x850');self.root.update()

    @unittest.skipUnless(os.name=='nt','Windows Shell integration test')
    def test_h_native_windows_drop_message(self):
        from ctypes import wintypes as w
        from offline_pdf.windows_drop import WM_DROPFILES
        self.assertTrue(self.app.file_drop.enabled)
        self.app.tool='merge';self.app.configure_form();self.app.clear_files()
        second=self.folder/'탐색기 공백 {문서}.PDF';second.write_bytes(self.source.read_bytes())
        paths=[str(self.source.resolve()),str(second.resolve())]
        payload=('\0'.join(paths)+'\0\0').encode('utf-16-le')
        # DROPFILES: DWORD pFiles; POINT pt; BOOL fNC; BOOL fWide.
        content=struct.pack('<IiiII',20,0,0,0,1)+payload
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GlobalAlloc.argtypes=[w.UINT,ctypes.c_size_t];kernel.GlobalAlloc.restype=w.HGLOBAL
        kernel.GlobalLock.argtypes=[w.HGLOBAL];kernel.GlobalLock.restype=ctypes.c_void_p
        kernel.GlobalUnlock.argtypes=[w.HGLOBAL];kernel.GlobalUnlock.restype=w.BOOL
        kernel.GlobalFree.argtypes=[w.HGLOBAL];kernel.GlobalFree.restype=w.HGLOBAL
        user=ctypes.WinDLL('user32',use_last_error=True)
        user.PostMessageW.argtypes=[w.HWND,w.UINT,ctypes.c_size_t,ctypes.c_ssize_t];user.PostMessageW.restype=w.BOOL
        handle=kernel.GlobalAlloc(0x42,len(content));self.assertTrue(handle)
        address=kernel.GlobalLock(handle)
        if not address:
            kernel.GlobalFree(handle);self.fail('Cannot lock test drop payload')
        ctypes.memmove(address,content,len(content));kernel.GlobalUnlock(handle)
        hwnd=self.app.file_list.winfo_id()
        if not user.PostMessageW(hwnd,WM_DROPFILES,handle,0):
            kernel.GlobalFree(handle);self.fail('Cannot post WM_DROPFILES')
        # The native handler owns the payload after the successful post.
        deadline=time.monotonic()+3
        while len(self.app.files)<2 and time.monotonic()<deadline:
            self.root.update();time.sleep(.01)
        self.assertEqual(self.app.files,paths)


if __name__=='__main__':unittest.main()
