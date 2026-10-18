import os
import ctypes
import struct
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pymupdf as pdf
from offline_pdf.app import App, TOOLS


class CardLayoutTests(unittest.TestCase):
    def test_more_columns_with_more_available_width_without_display_limits(self):
        # Test available layout space directly. A CI desktop can cap wm_geometry
        # requests at its physical screen size, regardless of the requested size.
        state=SimpleNamespace(show_all_tools=True,card_layout=None,card_columns=0,
                              home=SimpleNamespace(canvas=Mock()),cards_frame=Mock(),
                              cards={key:Mock() for key in TOOLS})
        state.home.canvas.winfo_height.return_value=800
        App.arrange_cards(state,620,force=True);small_columns=state.card_columns
        App.arrange_cards(state,1660,force=True);large_columns=state.card_columns
        self.assertGreater(large_columns,small_columns)
        self.assertEqual(len(state.cards),18)
        for card in state.cards.values():
            self.assertEqual(card.grid.call_count,2)
            compact,height=card.set_compact.call_args.args
            self.assertTrue(compact);self.assertLessEqual(height,68)


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
        self.assertTrue(self.app.sidebar.winfo_ismapped())

    def test_e_drop_unsupported_files_folder_and_cloud(self):
        blocked=self.folder/'OneDrive'/'private.pdf';blocked.parent.mkdir(exist_ok=True);blocked.write_bytes(self.source.read_bytes())
        self.app.tool='merge';self.app.configure_form();self.app.clear_files()
        self.app.on_files_drop([str(self.folder),str(self.folder/'unknown.txt'),str(blocked),str(self.source)])
        self.assertEqual(self.app.files,[str(self.source.resolve())])
        self.assertIn('지원하지 않는 항목 2개',self.app.status.get());self.assertIn('경로 1개 제외',self.app.status.get())

    def test_f_drop_image_for_image_tool(self):
        image=self.folder/'사진 한 장.png'
        with pdf.open(self.source) as source:source[0].get_pixmap().save(image)
        self.app.select_tool('images_pdf');self.app.clear_files()
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
        self.assertTrue(all(h<=68 for w,h in sizes))
        self.app.select_tool('redact');self.root.update()
        self.assertTrue(self.app.work.winfo_ismapped());self.assertFalse(self.app.home.winfo_ismapped())
        self.assertTrue(self.app.clear_preview_regions.winfo_ismapped())
        with patch.object(self.app,'busy',return_value=True):
            self.app.show_home();self.app.select_tool('merge')
        self.assertEqual(self.app.tool,'redact');self.assertTrue(self.app.work.winfo_ismapped())
        self.app.back_button.invoke();self.root.update();self.assertTrue(self.app.home.winfo_ismapped())
        self.app.all_tools_button.invoke();self.root.update()
        self.assertEqual(sum(card.winfo_ismapped() for card in self.app.cards.values()),6)

    def test_j_switch_image_category_preserves_and_marks_incompatible_files(self):
        self.app.select_tool('merge');self.app.files=[str(self.source)];self.app.sync_list()
        self.app.select_tool('rotate');self.assertEqual(self.app.files,[str(self.source)])
        self.app.select_tool('images_pdf');self.assertEqual(self.app.files,[str(self.source)])
        self.assertIn('사용 불가',self.app.file_list.rows[0][1])
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
        self.app.show_home()
        if not self.app.show_all_tools:self.app.toggle_tools()
        layouts=[]
        for width,height in [(900,650),(1280,720),(1920,1080)]:
            self.root.geometry(f'{width}x{height}');self.pump(.2)
            actual=(self.root.winfo_width(),self.root.winfo_height())
            with self.subTest(requested=(width,height),actual=actual):
                layouts.append((self.app.cards_frame.winfo_width(),self.app.card_columns))
                self.assertEqual(len(self.app.cards_frame.grid_slaves()),18)
                self.assertLessEqual(self.app.home.inner.winfo_height(),self.app.home.canvas.winfo_height()+2)
                for card in self.app.cards.values():
                    self.assertLessEqual(card.winfo_x()+card.winfo_width(),self.app.cards_frame.winfo_width()+1)
        # The live check uses actual space, not an assumption that a Windows
        # runner really created a 1920px window on a smaller virtual display.
        layouts.sort()
        self.assertGreaterEqual(layouts[-1][1],layouts[0][1])
        self.app.toggle_tools();self.root.geometry('1180x850');self.root.update()

    def test_m_preview_and_always_visible_run_button(self):
        self.root.geometry('900x650');self.app.select_tool('merge');self.root.update()
        self.assertFalse(self.app.preview_panel.winfo_ismapped())
        self.app.preview_button.invoke();self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.app.select_tool('redact');self.root.update()
        self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertTrue(self.app.clear_preview_regions.winfo_ismapped())
        button=self.app.run_button
        self.assertLessEqual(button.winfo_rooty()+button.winfo_height(),self.root.winfo_rooty()+self.root.winfo_height())
        self.app.select_tool('merge');self.root.geometry('1180x850');self.root.update()

    def wait_for_job(self):
        deadline=time.monotonic()+20
        while self.app.process is not None and time.monotonic()<deadline:
            self.root.update();time.sleep(.02)
        self.assertIsNone(self.app.process,'PDF worker did not finish')

    def test_n_merge_compress_delete_result_chain(self):
        self.app.cancel_continue();self.app.select_tool('merge')
        second=self.folder/'연속 작업 두번째.pdf';second.write_bytes(self.source.read_bytes())
        self.app.files=[str(self.source),str(second)];self.app.sync_list()
        self.app.save_mode.set('지정한 폴더');self.app.output.set(str(self.folder));self.app.auto_open.set(False)
        self.app.output_name.set('연속 병합.pdf')
        original_bytes=self.source.read_bytes()
        with patch('offline_pdf.app.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')):
            self.app.run();self.wait_for_job()
            merged=self.app.result_files[0];merged_bytes=Path(merged).read_bytes()
            self.assertEqual(str(self.app.next_button.cget('state')),'normal')
            self.app.next_button.invoke();self.root.update()
            self.assertTrue(self.app.home.winfo_ismapped())
            self.assertEqual(self.app.file_list.rows[0][2],merged)
            self.assertFalse(self.app.cards['images_pdf'].enabled)
            self.app.cards['compress'].activate();self.root.update()
            self.assertEqual(self.app.files,[merged]);self.assertEqual(self.app.tool,'compress')
            self.assertEqual(self.app.output.get(),str(self.folder))
            self.app.run();self.assertEqual(str(self.app.next_button.cget('state')),'disabled');self.wait_for_job()
            compressed=self.app.result_files[0];compressed_bytes=Path(compressed).read_bytes()
            self.app.next_button.invoke();self.app.cards['delete'].activate();self.root.update()
            self.assertEqual(self.app.files,[compressed]);self.assertEqual(self.app.tool,'delete')
            self.app.options['pages'].set('2');self.app.run();self.wait_for_job()
        final=self.app.result_files[0]
        with pdf.open(final) as doc:
            self.assertEqual(len(doc),3)
            self.assertEqual([page.get_text().strip() for page in doc],['FIRST','FIRST','SECOND'])
        # Windows may use an 8.3 alias (RUNNER~1) for the same physical folder.
        for output in (merged,compressed,final):
            self.assertTrue(Path(output).parent.parent.samefile(self.folder))
        self.assertEqual(self.source.read_bytes(),original_bytes)
        self.assertEqual(Path(merged).read_bytes(),merged_bytes)
        self.assertEqual(Path(compressed).read_bytes(),compressed_bytes)

    def test_o_pending_chain_cancel_missing_file_and_busy(self):
        before=list(self.app.files)
        self.app.continue_with_result();self.root.update()
        self.app.select_tool('images_pdf')
        self.assertEqual(self.app.files,before)
        self.app.chain_cancel_button.invoke();self.root.update()
        self.assertIsNone(self.app.pending_results)
        self.assertTrue(all(card.enabled for card in self.app.cards.values()))
        self.assertEqual(self.app.files,before)
        with patch.object(self.app,'busy',return_value=True):self.app.continue_with_result()
        self.assertIsNone(self.app.pending_results)
        saved=self.app.result_files
        try:
            self.app.result_files=(str(self.folder/'missing-result.pdf'),)
            self.app.continue_with_result()
            with patch('offline_pdf.app.messagebox.showinfo') as notice:self.app.select_tool('compress')
            notice.assert_called_once();self.assertEqual(self.app.files,before)
            self.assertIsNotNone(self.app.pending_results)
        finally:self.app.result_files=saved;self.app.cancel_continue()

    def test_p_image_results_continue_and_text_results_stop(self):
        self.app.select_tool('pdf_images');self.app.files=[str(self.source)];self.app.sync_list()
        self.app.options['dpi'].set('72');self.app.options['format'].set('PNG')
        self.app.save_mode.set('지정한 폴더');self.app.output.set(str(self.folder))
        with patch('offline_pdf.app.messagebox.askokcancel',return_value=True),patch('offline_pdf.app.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')):
            self.app.run();self.wait_for_job();images=self.app.result_files
            self.assertEqual(len(images),2)
            self.app.continue_with_result();self.root.update()
            self.assertEqual({key for key,card in self.app.cards.items() if card.enabled},{'images_pdf'})
            self.assertTrue(self.app.show_all_tools)
            self.app.cards['images_pdf'].activate();self.assertEqual(self.app.files,list(images))
            self.app.run();self.wait_for_job()
            with pdf.open(self.app.result_files[0]) as doc:self.assertEqual(len(doc),2)
            self.app.select_tool('text');self.app.files=[str(self.source)];self.app.sync_list()
            self.app.run();self.wait_for_job()
            self.assertEqual({Path(p).suffix for p in self.app.result_files},{'.txt'})
            self.assertEqual(str(self.app.next_button.cget('state')),'disabled')

    def test_q_failed_job_does_not_offer_previous_results(self):
        self.app.select_tool('merge');self.app.files=[str(self.source)];self.app.sync_list()
        self.app.output_name.set('CON.pdf')
        with patch('offline_pdf.app.messagebox.showerror') as error:
            self.app.run();self.wait_for_job();error.assert_called_once()
        self.assertEqual(self.app.result_files,())
        self.assertIsNone(self.app.result_folder)
        self.assertEqual(str(self.app.next_button.cget('state')),'disabled')
        self.assertFalse(list(self.folder.glob('.offline-pdf-*')))

    def pump(self,seconds=.3):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:self.root.update();time.sleep(.01)

    def test_r_drag_pages_rotate_delete_save_and_continue(self):
        source=self.folder/'페이지 정리 시험.pdf'
        with pdf.open() as doc:
            for i in range(8):doc.new_page().insert_text((72,72),f'PAGE {i+1}')
            doc.save(source)
        original=source.read_bytes();self.app.cancel_continue();self.app.select_tool('extract');self.app.add_paths([str(source)]);self.pump()
        o=self.app.organizer;c=o.canvas
        self.assertEqual(len(o.model.items),8);self.assertTrue(o.winfo_ismapped());self.assertFalse(self.app.columns.winfo_ismapped())
        x1=int(o.cellw*.5);x3=int(o.cellw*2.8)
        c.event_generate('<ButtonPress-1>',x=x1,y=100);self.root.update()
        c.event_generate('<B1-Motion>',x=x3,y=110);self.root.update()
        self.assertIsNotNone(o.boundary)
        c.event_generate('<ButtonRelease-1>',x=x3,y=110);self.root.update()
        self.assertEqual([p[1] for p in o.model.items],[1,2,0,3,4,5,6,7])
        o.model.selected={1};o.rotate();o.model.selected={2};o.delete()
        self.assertEqual(o.model.plan()[1],{'page':0,'rotation':90})
        o.model.selected={1};o.enlarge();self.pump();self.assertTrue(self.app.preview_panel.winfo_ismapped())
        self.assertEqual(self.app.page_index,0);self.app.turn(1);self.assertEqual(self.app.page_index,3)
        self.app.hide_preview();self.root.update();self.assertEqual(o.model.plan()[1]['rotation'],90)
        self.app.save_mode.set('지정한 폴더');self.app.output.set(str(self.folder))
        with patch('offline_pdf.app.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')):
            self.app.run();self.wait_for_job()
        result=self.app.result_files[0]
        with pdf.open(result) as doc:
            self.assertEqual([p.get_text().strip() for p in doc],['PAGE 3','PAGE 1','PAGE 4','PAGE 5','PAGE 6','PAGE 7','PAGE 8'])
            self.assertEqual(doc[1].rotation,90)
        self.assertEqual(source.read_bytes(),original)
        self.app.continue_with_result();self.app.select_tool('compress');self.assertEqual(self.app.files,[result])

    def test_s_width_fit_zoom_and_scrolled_redaction_coordinates(self):
        self.app.select_tool('redact');self.app.files=[str(self.source)];self.app.sync_list();self.app.show_preview();self.pump()
        self.app.set_preview_mode('width');self.pump()
        self.assertGreater(self.app.canvas.winfo_width(),self.app.content_host.winfo_width()*.85)
        width_scale=self.app.preview_scale
        self.assertAlmostEqual(width_scale,(self.app.canvas.winfo_width()-24)/self.app.preview_rect[0],places=3)
        self.assertLess(self.app.canvas.winfo_height(),self.root.winfo_height())
        self.assertGreater(float(self.app.canvas.cget('scrollregion').split()[-1]),self.app.canvas.winfo_height())
        self.app.set_preview_mode('page');self.pump();self.assertLess(self.app.preview_scale,width_scale)
        self.app.set_preview_mode('width');self.app.zoom_preview(.5);self.pump();self.app.canvas.xview_moveto(.2)
        start=SimpleNamespace(x=30,y=50);end=SimpleNamespace(x=170,y=160)
        a=self.app.canvas_point(start);b=self.app.canvas_point(end)
        self.app.regions={};self.app.draw_start(start);self.app.draw_move(end);self.app.draw_end(end)
        coords=self.app.regions[str(self.source)]['0'][0]
        for got,wanted in zip(coords,[a[0],a[1],b[0],b[1]]):self.assertAlmostEqual(got,wanted)
        self.app.clear_regions();self.app.preview_zoom=1.;self.app.select_tool('merge')

    def test_t_large_document_virtual_thumbnails_and_busy_lock(self):
        source=self.folder/'많은 페이지.pdf'
        with pdf.open() as doc:
            for i in range(150):doc.new_page().insert_text((72,72),str(i+1))
            doc.save(source)
        self.app.select_tool('extract');self.app.add_paths([str(source)]);self.pump()
        o=self.app.organizer;self.assertEqual(len(o.model.items),150);self.assertLessEqual(len(o.cache),20)
        o.scroll_to('moveto',1);self.pump();self.assertLessEqual(len(o.cache),40)
        self.assertGreater(o.canvas.yview()[0],.5)
        before=o.model.plan();o.model.selected={1}
        with patch.object(self.app,'busy',return_value=True):o.rotate();o.delete();o.reset();o.keyboard_move(1)
        self.assertEqual(o.model.plan(),before)
        o.scroll_to('moveto',0);o.model.selected={1};o.keyboard_move(1)
        self.assertEqual(o.model.items[1][1],0);o.undo();self.assertEqual(o.model.items[0][1],0)

    def test_u_menu_and_drop_hover_transitions(self):
        self.app.show_home();self.root.update();card=self.app.cards['merge'];card.highlight(True);self.pump(.22)
        self.assertGreater(card.hover_amount,.9);card.highlight(False);self.pump(.22);self.assertLess(card.hover_amount,.1)
        self.app.select_tool('merge');self.app.clear_files();self.app.hide_preview();self.root.update()
        self.app.drop_icon.event_generate('<Motion>',warp=True,x=15,y=15);self.pump(.3)
        self.assertTrue(self.app.drop_hover.active)
        self.assertGreater(self.app.drop_hover.tween.value,.9)
        self.app.back_button.event_generate('<Motion>',warp=True,x=5,y=5);self.pump(.3)
        self.assertFalse(self.app.drop_hover.active)
        self.assertGreaterEqual(self.app.back_button.winfo_height(),40)

    def test_v_encrypted_organizer_settings_and_source_replacement(self):
        source=self.folder/'암호 페이지.pdf'
        with pdf.open(self.source) as doc:doc.save(source,encryption=pdf.PDF_ENCRYPT_AES_256,user_pw='password',owner_pw='password')
        self.app.select_tool('extract');self.app.clear_files();self.app.add_paths([str(source)]);self.assertIsNone(self.app.organizer.model)
        dialog=self.app.organizer_settings();self.app.options['input_password'].set('password')
        buttons=dialog.winfo_children()[0].winfo_children()
        next(b for b in buttons if isinstance(b,tk.ttk.Button) and b.cget('text')=='확인').invoke()
        self.root.update();self.assertEqual(len(self.app.organizer.model.items),2)
        self.app.organizer.model.selected={1};self.app.organizer.rotate()
        with patch('offline_pdf.app.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')):
            self.app.run();self.wait_for_job()
        with pdf.open(self.app.result_files[0]) as doc:
            self.assertTrue(doc.needs_pass);self.assertTrue(doc.authenticate('password'));self.assertEqual(doc[0].rotation,90)
        self.app.add_paths([str(self.source)]);self.assertEqual(self.app.files,[str(source.resolve()),str(self.source.resolve())])
        self.assertEqual([p['rotation'] for p in self.app.organizer.model.plan()],[0,0])
        before=list(self.app.files);self.app.add_paths([str(self.source),str(source)]);self.assertEqual(self.app.files,before)

    def test_w_home_sidebar_repeated_feedback_and_n_file_split(self):
        self.root.geometry('1280x720');self.app.show_home();self.app.clear_files()
        source=self.folder/'나누기 열 쪽.pdf'
        with pdf.open() as doc:
            for i in range(10):doc.new_page().insert_text((50,80),f'PAGE {i+1}')
            doc.save(source)
        self.root.update();self.app.add_paths([str(source)]);self.pump(.1)
        self.assertTrue(self.app.home.winfo_ismapped());self.assertTrue(self.app.sidebar.winfo_ismapped())
        self.assertIn('10쪽',self.app.file_list.rows[0][1]);self.assertGreater(self.app.file_list.flash_value,0)
        serial=self.app.feedback.serial
        self.app.status.set('0개 추가 · 전체 1개');self.app.status.set('0개 추가 · 전체 1개')
        self.assertEqual(self.app.feedback.serial,serial+2)
        self.app.select_tool('split');self.app.options['split_mode'].set('N개 파일로 나누기')
        self.app.options['split_count'].set('3');self.app.options['split_starts'].set('5,8')
        self.assertIn('1–4쪽',self.app.split_summary.cget('text'));self.assertIn('8–10쪽',self.app.split_summary.cget('text'))
        self.app.save_mode.set('지정한 폴더');self.app.output.set(str(self.folder));self.app.auto_open.set(False)
        with patch('offline_pdf.app.messagebox.showerror',side_effect=AssertionError('Unexpected UI error')):
            self.app.run();self.root.update();self.assertTrue(self.app.progress.winfo_ismapped());self.wait_for_job()
        lengths=[]
        for path in self.app.result_files:
            with pdf.open(path) as doc:lengths.append(len(doc))
        self.assertEqual(lengths,[4,3,3]);self.root.update()
        self.assertFalse(self.app.progress.winfo_ismapped());self.assertTrue(self.app.result_actions.winfo_ismapped())
        self.root.geometry('1180x850')

    def test_y_all_forms_keep_controls_and_actions_inside_small_window(self):
        self.app.cancel_continue();self.root.geometry('900x650');self.app.clear_files()
        for tool in TOOLS:
            self.app.select_tool(tool);self.pump(.08)
            bottom=self.root.winfo_rooty()+self.root.winfo_height()-43
            for key,cell in self.app.form_cells:
                if cell.winfo_ismapped():
                    self.assertLessEqual(cell.winfo_rooty()+cell.winfo_height(),bottom,(tool,key))
                    self.assertLessEqual(cell.winfo_rootx()+cell.winfo_width(),self.root.winfo_rootx()+self.root.winfo_width(),(tool,key))
            self.assertLessEqual(self.app.run_button.winfo_rooty()+self.app.run_button.winfo_height(),bottom,tool)
        self.root.geometry('1180x850')

    def test_z_image_formats_and_jpg_default(self):
        from PIL import Image
        from offline_pdf.images import EXPORT_FORMATS
        self.app.cancel_continue()
        self.app.tool='pdf_images';self.app.configure_form()
        self.assertEqual(self.app.options['format'].get(),'JPG')
        self.app.tool='images_pdf';self.app.configure_form();self.app.clear_files()
        paths=[]
        for extension,fmt in [('bmp','BMP'),('gif','GIF'),('tif','TIFF'),('tiff','TIFF'),
                              ('webp','WEBP'),('heic','HEIF'),('heif','HEIF')]:
            path=self.folder/('추가한 이미지.'+extension.upper())
            with Image.new('RGB',(64,32),'red') as im:im.save(path,format=fmt)
            paths.append(str(path.resolve()))
        self.app.add_paths(paths)
        self.assertEqual(self.app.files,paths)
        self.app.file_list.selection_clear(0,'end');self.app.file_list.selection_set(5)
        self.app.refresh_preview(reset=True);self.root.update()
        self.assertIsNotNone(self.app.preview_rect)
        for extension in EXPORT_FORMATS:
            self.assertEqual(self.app.result_input_tools([Path('result.'+extension.lower())]),{'images_pdf'})

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
