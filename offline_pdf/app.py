"""Korean native desktop interface using only Python's bundled Tkinter."""
from __future__ import annotations

import base64
import multiprocessing as mp
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import time
import uuid
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pymupdf as pdf
from .engine import UserError, check_local_path, disable_network, open_pdf, worker
from . import __version__
from .windows_drop import NativeFileDrop
from .ui import CARD_TEXT, POPULAR, PANEL, MUTED, icon


TOOLS = {
    'merge': ('PDF 합치기', '파일 목록 순서대로 모든 페이지를 한 PDF로 합칩니다.'),
    'split': ('PDF 나누기', '선택한 페이지마다 별도 PDF를 만듭니다.'),
    'extract': ('페이지 정리', '입력한 순서로 추출합니다. 예: 3,1,2 또는 1-3,5'),
    'delete': ('페이지 삭제', '입력한 페이지를 삭제합니다. 원본은 그대로 보관합니다.'),
    'rotate': ('페이지 회전', '선택한 페이지를 시계 방향으로 회전합니다.'),
    'compress': ('용량 줄이기', '무손실 정리·압축입니다. 파일에 따라 용량이 늘 수도 있습니다.'),
    'pdf_images': ('PDF → 이미지', '페이지를 JPG·PNG로 저장합니다. 암호 보호는 이미지에 적용되지 않습니다.'),
    'images_pdf': ('이미지 → PDF', 'JPG·PNG 파일을 목록 순서대로 A4 PDF로 만듭니다.'),
    'protect': ('암호 설정', '파일을 열 때 필요한 암호를 AES-256 방식으로 설정합니다.'),
    'unlock': ('암호 해제', '소유자 암호를 알고 있는 PDF의 암호를 해제합니다.'),
    'watermark': ('워터마크', '선택한 페이지 가운데에 한글·영문 문구를 추가합니다.'),
    'number': ('쪽 번호', '선택한 페이지 순서대로 아래쪽에 번호를 넣습니다.'),
    'stamp': ('서명·직인 이미지', '오른쪽 아래에 서명 이미지를 넣습니다. 인증서 전자서명 기능은 아닙니다.'),
    'crop': ('여백 자르기', '네 방향 여백을 같은 크기로 가립니다. 가려진 정보는 영구 삭제되지 않습니다.'),
    'text': ('텍스트 추출', '문자를 TXT로 저장합니다. 암호 보호는 TXT에 적용되지 않습니다. 스캔 문서는 OCR을 사용하세요.'),
    'redact': ('영역 영구 삭제', '미리보기에서 드래그해 영역을 지정하세요. 복사·추출과 이미지로 결과를 확인하세요.'),
    'clean': ('문서 부가정보 정리', '문서 속성·첨부파일·JavaScript·주석 응답 등을 정리합니다. 본문 개인정보 삭제 기능은 아닙니다.'),
    'ocr': ('검색 가능한 PDF', '선택 기능: 오프라인 OCR 언어자료가 필요합니다. 글자·표·서명 모양을 복원하는 기능은 아닙니다.'),
}


class App:
    def __init__(self, root):
        self.root=root; self.files=[]; self.regions={}; self.tool='merge'
        self.page_index=0; self.preview_scale=1; self.preview_rect=None; self.preview_photo=None
        self.process=None; self.events=None; self.cancel=None; self.cancel_at=None; self.stage=None
        self.result_folder=None; self.drag_start=None; self.drag_id=None; self.options={}
        from .layout import build
        build(self)
        self.file_drop=None
        try:
            self.file_drop=NativeFileDrop(root,self.on_files_drop,
                (self.file_list,self.canvas,self.drop_area,self.drop_title,self.add_button))
        except (OSError,AttributeError):
            self.drop_title.config(text='파일 추가 버튼으로 파일을 선택하세요')
        root.protocol('WM_DELETE_WINDOW',self.close)
        self.configure_form();root.after(150,self.poll)

    def busy(self):return self.process is not None

    def arrange_cards(self,width,force=False):
        columns=3 if width>=850 else 2 if width>=550 else 1
        if columns==self.card_columns and not force:return
        self.card_columns=columns
        keys=list(POPULAR)+[key for key in CARD_TEXT if key not in POPULAR] if self.show_all_tools else POPULAR
        for card in self.cards.values():card.grid_forget()
        for col in range(3):self.cards_frame.columnconfigure(col,weight=1 if col<columns else 0,uniform='cards' if col<columns else '')
        for index,key in enumerate(keys):
            self.cards[key].grid(row=index//columns,column=index%columns,sticky='ew',padx=6,pady=(0,12))

    def toggle_tools(self):
        self.show_all_tools=not self.show_all_tools
        self.all_tools_button.config(text='접기  ⌃' if self.show_all_tools else '전체 도구 보기  ⌄')
        self.home_section.config(text='전체 도구' if self.show_all_tools else '자주 쓰는 도구')
        self.arrange_cards(self.cards_frame.winfo_width(),force=True)

    def select_tool(self,key):
        if self.busy() or key not in TOOLS:return
        previous=self.tool
        self.tool=key
        if (previous=='images_pdf') != (key=='images_pdf'):
            self.files=[];self.regions={};self.sync_list()
        if previous!=key:self.regions={}
        self.home.pack_forget();self.work.pack(fill='both',expand=True)
        self.configure_form();self.work_scroll.canvas.yview_moveto(0)
        self.root.after_idle(lambda:self.refresh_preview(reset=True))

    def show_home(self):
        if self.busy():return
        self.work.pack_forget();self.home.pack(fill='both',expand=True)

    def toggle_preview(self):
        if self.tool=='redact':return
        if self.preview_panel.winfo_manager():
            self.preview_panel.pack_forget();self.preview_button.config(text='미리보기 펼치기')
        else:
            self.preview_panel.pack(fill='both',expand=True,pady=(16,0));self.preview_button.config(text='미리보기 접기')
            self.schedule_preview()

    def change_save_mode(self,event=None):
        if self.busy():return
        if self.save_mode.get()=='원본 파일과 같은 폴더' and self.files:
            self.output.set(str(Path(self.files[0]).parent))
        elif self.save_mode.get()=='지정한 폴더':self.choose_output()

    def field(self,label,key,default='',choices=None,secret=False,browse=None):
        row=2*len(self.options);var=tk.StringVar(value=default);self.options[key]=var
        ttk.Label(self.form,text=label,style='Panel.TLabel').grid(row=row,column=0,columnspan=2,sticky='w',pady=(8,5))
        if choices:
            widget=ttk.Combobox(self.form,textvariable=var,values=choices,state='readonly',width=18)
        else:
            widget=ttk.Entry(self.form,textvariable=var,width=20,show='●' if secret else '')
        widget.grid(row=row+1,column=0,sticky='ew')
        if key=='input_password':widget.bind('<FocusOut>',lambda e:self.refresh_preview())
        if browse:
            def pick():
                path=filedialog.askdirectory(parent=self.root) if browse=='dir' else filedialog.askopenfilename(parent=self.root,filetypes=[('이미지','*.png *.jpg *.jpeg')])
                if path:var.set(path)
            ttk.Button(self.form,text='선택',command=pick).grid(row=row+1,column=1,padx=(5,0))

    def configure_form(self):
        for w in self.form.winfo_children():w.destroy()
        self.options={};title,desc=TOOLS[self.tool];self.title.config(text=title);self.description.config(text=desc)
        self.task_icon.delete('all');icon(self.task_icon,self.tool,12,12)
        self.run_button.config(text=CARD_TEXT[self.tool][0]+'  →')
        self.drop_hint.config(text='JPG·PNG 이미지' if self.tool=='images_pdf' else 'PDF 파일')
        if self.tool=='redact':
            self.preview_panel.pack(fill='both',expand=True,pady=(16,0));self.preview_button.config(text='영역 선택용 미리보기',state='disabled')
        else:
            self.preview_panel.pack_forget();self.preview_button.config(text='미리보기 펼치기',state='normal')
        self.output_name.set('합친문서.pdf' if self.tool=='merge' else '이미지문서.pdf')
        if self.tool in ('merge','images_pdf'):self.name_frame.pack(fill='x',pady=(13,0),before=self.name_frame.master.winfo_children()[-1])
        else:self.name_frame.pack_forget()
        if self.tool=='redact':self.region_controls.pack(fill='x')
        else:self.region_controls.pack_forget()
        if self.tool not in ('merge','images_pdf','unlock','protect','compress','clean','redact'):
            self.field('페이지', 'pages', '')
        self.field('입력 암호','input_password',secret=True)
        if self.tool in ('protect','merge','images_pdf'):self.field('새 암호','output_password',secret=True)
        if self.tool=='rotate':self.field('시계 방향 각도','angle','90',['90','180','270'])
        if self.tool=='pdf_images':
            self.field('해상도 DPI','dpi','150',['72','100','150','200','300']);self.field('형식','format','PNG',['PNG','JPG'])
        if self.tool=='images_pdf':self.field('A4 방향','orientation','세로',['세로','가로'])
        if self.tool=='watermark':
            self.field('문구','text','내부 업무용');self.field('글자 크기','font_size','24');self.field('불투명도','opacity','0.25')
        if self.tool=='number':self.field('시작 번호','start','1')
        if self.tool=='crop':self.field('여백 mm','margin','10')
        if self.tool=='stamp':
            self.field('서명 이미지','stamp_path',browse='file');self.field('너비 pt','stamp_width','100')
        if self.tool=='ocr':
            root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parents[1]))
            self.field('언어자료 폴더','tessdata',str(root/'tessdata'),browse='dir');self.field('문서 언어','language','kor+eng',['kor+eng','kor','eng'])
        self.security.config(text='페이지를 비워 두면 전체 페이지를 처리합니다.' if 'pages' in self.options else '')
        if 'pages' in self.options:self.security.pack(anchor='w',pady=(12,0))
        else:self.security.pack_forget()
        self.update_file_summary()
        self.update_region_status()

    def add_files(self):
        if self.busy():return
        image=self.tool=='images_pdf'
        paths=filedialog.askopenfilenames(parent=self.root,title='처리할 파일을 선택하세요',filetypes=[('이미지','*.jpg *.jpeg *.png')] if image else [('PDF 문서','*.pdf')])
        if paths:self.add_paths(paths)

    def on_files_drop(self, paths):
        if not self.busy() and self.home.winfo_ismapped():self.select_tool(self.tool)
        self.add_paths(paths)

    def add_paths(self, paths):
        if self.busy():
            self.status.set('작업 중에는 파일을 추가할 수 없습니다. 완료 후 다시 끌어놓으세요.')
            return
        extensions={'.jpg','.jpeg','.png'} if self.tool=='images_pdf' else {'.pdf'}
        expected='JPG·PNG' if self.tool=='images_pdf' else 'PDF'
        known={os.path.normcase(str(Path(path).resolve())) for path in self.files}
        added=duplicates=unsupported=blocked=0
        for path in paths:
            candidate=Path(path)
            if candidate.suffix.lower() not in extensions:
                unsupported+=1
                continue
            try:
                candidate=check_local_path(candidate)
                if not candidate.is_file():
                    blocked+=1
                    continue
            except (UserError,OSError,RuntimeError):
                blocked+=1
                continue
            key=os.path.normcase(str(candidate))
            if key in known:
                duplicates+=1
                continue
            known.add(key);self.files.append(str(candidate));added+=1
        if added:
            self.sync_list();self.refresh_preview(reset=True)
        details=[f'{added}개 추가',f'전체 {len(self.files)}개']
        if duplicates:details.append(f'중복 {duplicates}개 제외')
        if unsupported:details.append(f'지원하지 않는 항목 {unsupported}개 제외 ({expected} 파일만 추가 가능)')
        if blocked:details.append(f'접근 불가·동기화·네트워크 경로 {blocked}개 제외')
        self.status.set(' · '.join(details))

    def sync_list(self):
        self.file_list.delete(0,'end')
        for i,path in enumerate(self.files):self.file_list.insert('end',f'{i+1:02d}  {Path(path).name}')
        if self.files:self.file_list.selection_set(0)
        self.update_file_summary()
        self.status.set(f'{len(self.files)}개 파일 · 목록의 위에서 아래 순서로 처리합니다.')

    def update_file_summary(self):
        self.file_count.config(text=f'선택한 파일  {len(self.files)}개')
        self.summary.set(f'파일 {len(self.files)}개 선택됨' if self.files else '파일을 추가해 주세요.')
        self.run_button.config(state='disabled' if self.busy() or not self.files else 'normal')
        if self.files and self.save_mode.get()=='원본 파일과 같은 폴더':self.output.set(str(Path(self.files[0]).parent))

    def remove_files(self):
        if self.busy():return
        for i in reversed(self.file_list.curselection()):self.files.pop(i)
        self.regions={};self.sync_list();self.refresh_preview(reset=True)

    def clear_files(self):
        if self.busy():return
        self.files=[];self.regions={};self.sync_list();self.refresh_preview(reset=True)

    def move(self,delta):
        if self.busy():return
        sel=self.file_list.curselection()
        if len(sel)!=1:return
        i=sel[0];j=i+delta
        if 0<=j<len(self.files):
            self.files[i],self.files[j]=self.files[j],self.files[i];self.sync_list();self.file_list.selection_clear(0,'end');self.file_list.selection_set(j);self.refresh_preview(reset=True)

    def selected_file(self):
        sel=self.file_list.curselection()
        return self.files[sel[0] if sel else 0] if self.files else None

    def schedule_preview(self):
        if self.preview_timer:self.root.after_cancel(self.preview_timer)
        self.preview_timer=self.root.after(250,self.refresh_preview)

    def refresh_preview(self,reset=False):
        self.preview_timer=None;self.canvas.delete('all');self.preview_rect=None
        if reset:self.page_index=0
        path=self.selected_file()
        if not path:
            text='파일을 추가하면 여기에서 미리 볼 수 있습니다.'
            if self.file_drop and self.file_drop.enabled:text='파일을 여기에 끌어놓거나\n파일 추가 버튼으로 선택하세요.'
            self.canvas.create_text(15,25,anchor='nw',text=text)
            self.page_label.config(text='미리보기');return
        try:
            check_local_path(path)
            pw=self.options.get('input_password');password=pw.get() if pw else ''
            if Path(path).suffix.lower()=='.pdf':doc,_=open_pdf(path,password,extraction=True)
            else:doc=pdf.open(path)
            try:
                self.page_index=max(0,min(self.page_index,doc.page_count-1));page=doc[self.page_index]
                w=max(self.canvas.winfo_width()-24,150);h=max(self.canvas.winfo_height()-24,200)
                self.preview_scale=min(w/page.rect.width,h/page.rect.height,1.5)
                pix=page.get_pixmap(matrix=pdf.Matrix(self.preview_scale,self.preview_scale),alpha=False,colorspace=pdf.csRGB)
                self.preview_photo=tk.PhotoImage(data=base64.b64encode(pix.tobytes('png')))
                self.canvas.create_image(12,12,anchor='nw',image=self.preview_photo)
                self.preview_rect=(page.rect.width,page.rect.height)
                self.page_label.config(text=f'{self.page_index+1} / {doc.page_count}쪽')
                if self.tool=='redact':
                    for coords in self.regions.get(path,{}).get(str(self.page_index),[]):
                        self.canvas.create_rectangle(*[12+c*self.preview_scale for c in coords],outline='#d32f2f',width=2,stipple='gray50',fill='#d32f2f')
            finally:doc.close()
        except Exception:
            self.canvas.create_text(15,25,anchor='nw',width=320,text='미리보기를 열 수 없습니다.\n입력 암호와 파일 형식을 확인하세요.')
        self.update_region_status()

    def turn(self,delta):
        self.page_index=max(0,self.page_index+delta);self.refresh_preview()

    def draw_start(self,event):
        if self.tool!='redact' or not self.preview_rect or self.busy():return
        self.drag_start=self.canvas_point(event)
        self.drag_id=self.canvas.create_rectangle(event.x,event.y,event.x,event.y,outline='#d32f2f',width=2)

    def canvas_point(self,event):
        return (max(0,min(self.preview_rect[0],(event.x-12)/self.preview_scale)),max(0,min(self.preview_rect[1],(event.y-12)/self.preview_scale)))

    def draw_move(self,event):
        if self.drag_start and self.drag_id:
            x,y=self.drag_start;self.canvas.coords(self.drag_id,12+x*self.preview_scale,12+y*self.preview_scale,event.x,event.y)

    def draw_end(self,event):
        if not self.drag_start:return
        x,y=self.drag_start;xx,yy=self.canvas_point(event);self.drag_start=None
        if abs(x-xx)>3 and abs(y-yy)>3:
            coords=[min(x,xx),min(y,yy),max(x,xx),max(y,yy)]
            self.regions.setdefault(self.selected_file(),{}).setdefault(str(self.page_index),[]).append(coords)
        self.refresh_preview()

    def clear_regions(self):
        if self.busy():return
        self.regions.get(self.selected_file(),{}).pop(str(self.page_index),None);self.refresh_preview()

    def update_region_status(self):
        count=sum(len(rects) for regions in self.regions.values() for rects in regions.values())
        self.region_status.config(text=f'삭제 영역 {count}개 · 영구 삭제는 한 파일씩 처리합니다.')

    def choose_output(self):
        if self.busy():return
        path=filedialog.askdirectory(parent=self.root,title='승인된 로컬 저장 폴더를 선택하세요')
        if path:self.output.set(path);self.save_mode.set('지정한 폴더')

    def run(self):
        if self.busy():return
        if not self.files:messagebox.showinfo('파일 추가','처리할 파일을 먼저 추가하세요.',parent=self.root);return
        if self.tool=='redact' and len(self.files)!=1:
            messagebox.showinfo('파일 선택','영구 삭제는 한 파일씩 처리하세요.',parent=self.root);return
        try:check_local_path(self.output.get())
        except UserError as exc:messagebox.showinfo('저장 폴더',str(exc),parent=self.root);return
        if not Path(self.output.get()).is_dir():
            messagebox.showinfo('저장 폴더','결과를 저장할 폴더를 선택하세요.',parent=self.root);return
        if self.tool=='delete' and not self.options['pages'].get().strip():
            messagebox.showinfo('페이지 지정','삭제할 페이지를 입력하세요.',parent=self.root);return
        if self.tool in ('redact','unlock','pdf_images','text','crop'):
            notes={
                'redact':'지정 영역을 실제 삭제하며 문서의 첨부파일·양식 필드·주석·링크·속성도 정리합니다. 잘린 페이지는 지원하지 않습니다. 지정 영역 밖의 정보는 남으므로 결과를 확인하세요.',
                'unlock':'결과 PDF의 암호가 제거됩니다.',
                'pdf_images':'결과 이미지에는 원본 PDF의 암호 보호가 적용되지 않습니다.',
                'text':'결과 TXT에는 원본 PDF의 암호 보호가 적용되지 않습니다.',
                'crop':'여백 자르기는 내용을 숨기는 기능입니다. 개인정보 영구 삭제에는 “영역 영구 삭제”를 사용하세요.'}
            if not messagebox.askokcancel('작업 확인',notes[self.tool]+'\n\n계속하시겠습니까?',parent=self.root):return
        try:
            for path in self.files:
                if Path(path).suffix.lower()=='.pdf':
                    src,_=open_pdf(path,self.options['input_password'].get(),extraction=self.tool in ('text','pdf_images','ocr'))
                    try:signed=src.get_sigflags()>0
                    finally:src.close()
                    if signed and not messagebox.askokcancel('전자서명 문서','수정하면 기존 전자서명 검증 상태가 달라질 수 있습니다. 원본은 보존됩니다. 계속하시겠습니까?',parent=self.root):return
        except UserError as exc:messagebox.showerror('파일 확인',str(exc),parent=self.root);return
        job={'tool':self.tool,'files':list(self.files),'output':self.output.get(),'options':{k:v.get() for k,v in self.options.items() if k!='hint'}}
        if self.tool in ('merge','images_pdf'):job['options']['output_name']=self.output_name.get()
        if self.tool=='redact':job['options']['regions']=self.regions.get(self.files[0],{})
        job['stage_id']=uuid.uuid4().hex
        ctx=mp.get_context('spawn');self.events=ctx.Queue();self.cancel=ctx.Event();self.cancel_at=None
        self.stage=str(Path(self.output.get()).resolve()/('.offline-pdf-'+job['stage_id']))
        self.process=ctx.Process(target=worker,args=(job,self.events,self.cancel));self.dead_at=None
        try:self.process.start()
        except Exception:
            self.process=None;self.cleanup_stage();self.events.close();self.events=None
            messagebox.showerror('실행 오류','작업 프로세스를 실행할 수 없습니다. 백신·실행 권한·배포파일 구성을 확인하세요.',parent=self.root);return
        # Remove secrets from visible controls after the child has its own copy.
        for key in ('input_password','output_password'):
            if key in self.options:self.options[key].set('')
        self.run_button.config(state='disabled');self.cancel_button.config(state='normal');self.open_button.config(state='disabled')
        self.back_button.config(state='disabled');self.save_mode_combo.config(state='disabled')
        self.status.set('처리 중입니다. 원본 파일은 변경하지 않습니다.');self.progress['value']=0

    def cancel_job(self):
        if self.process and self.cancel_at is None:
            self.cancel.set();self.cancel_at=time.monotonic();self.status.set('작업을 취소하고 임시 결과를 정리하고 있습니다.')

    def cleanup_stage(self):
        clean=True
        if self.stage:
            path=Path(self.stage)
            if path.name.startswith('.offline-pdf-'):shutil.rmtree(path,ignore_errors=True)
            clean=not path.exists()
            self.stage=None
        return clean

    def finish(self,message):
        if self.process:
            self.process.join(timeout=.2)
            if self.process.is_alive():self.process.terminate();self.process.join(timeout=2)
        self.process=None;self.cancel_at=None;clean=self.cleanup_stage()
        if self.events:self.events.close();self.events=None
        self.update_file_summary();self.cancel_button.config(state='disabled')
        self.back_button.config(state='normal');self.save_mode_combo.config(state='readonly')
        self.status.set(message if clean else message+' 임시자료가 남았습니다. 저장 폴더의 .offline-pdf- 폴더를 확인하세요.')

    def poll(self):
        if self.process:
            try:
                while True:
                    event=self.events.get_nowait();kind=event['type']
                    if kind=='stage':self.stage=event['folder']
                    elif kind=='progress':
                        self.progress['value']=100*event['current']/max(1,event['total']);self.status.set(event['label'])
                    elif kind=='done':
                        self.result_folder=event['folder'];self.finish('완료했습니다. “결과 폴더 열기”에서 확인하세요.');self.progress['value']=100;self.open_button.config(state='normal')
                        if self.auto_open.get():self.open_result()
                        break
                    elif kind=='cancelled':self.finish('작업을 취소했습니다. 원본은 그대로 보관됩니다.');break
                    elif kind=='error':
                        self.finish('작업을 완료하지 못했습니다. 원본은 그대로 보관됩니다.');messagebox.showerror('처리 결과',event['message'],parent=self.root);break
            except queue.Empty:pass
            if self.process:
                if self.cancel_at and time.monotonic()-self.cancel_at>3:
                    self.finish('작업을 취소했습니다. 결과 폴더의 임시자료 정리 여부를 확인하세요.')
                elif not self.process.is_alive():
                    # Allow the multiprocessing queue feeder to flush a final message.
                    if getattr(self,'dead_at',None) is None:self.dead_at=time.monotonic()
                    elif time.monotonic()-self.dead_at>.6:self.finish('작업 프로세스가 종료되었습니다. 원본은 변경되지 않았습니다.');self.dead_at=None
                else:self.dead_at=None
        self.root.after(150,self.poll)

    def open_result(self):
        if not self.result_folder:return
        try:
            if os.name=='nt':os.startfile(self.result_folder)
            elif sys.platform=='darwin':subprocess.Popen(['open',self.result_folder])
            else:subprocess.Popen(['xdg-open',self.result_folder])
        except OSError:self.status.set('저장은 완료했습니다. 파일 탐색기에서 결과 폴더를 확인하세요.')

    def close(self):
        if self.process:
            if not messagebox.askokcancel('종료','실행 중인 작업을 취소하고 종료하시겠습니까?',parent=self.root):return
            self.cancel.set();self.process.join(timeout=.5)
            if self.process.is_alive():self.process.terminate();self.process.join(timeout=2)
            self.cleanup_stage()
        if self.file_drop:self.file_drop.close()
        self.root.destroy()

    def help(self):
        messagebox.showinfo('사용 안내',
            '① 작업 선택 → ② 파일 추가 → ③ 설정 → ④ 실행\n\n'
            'Windows 탐색기에서 파일을 창 안으로 끌어놓아 추가할 수 있습니다.\n'
            '여러 파일을 한 번에 추가할 수 있으며 중복은 제외합니다.\n'
            '이미지를 추가할 때는 먼저 “이미지 → PDF”를 선택하세요.\n'
            '페이지 공란은 전체 페이지입니다. 예: 1-3,5 / 역순: 3-1\n'
            '합치기는 목록 순서입니다. 파일을 선택하고 위로·아래로 이동하세요.\n'
            '결과는 선택한 폴더 안에 새 PDF결과 폴더로 저장됩니다.\n'
            '기존 파일을 덮어쓰지 않으며 실패한 작업 결과는 정리합니다.\n\n'
            '영구 삭제: 미리보기에서 드래그 → 실행 → 결과를 검색·복사·추출해 확인\n'
            'OCR: 배포 담당자가 준비한 kor/eng.traineddata 폴더를 선택\n'
            'Word·Excel·PPT·HWP·PDF/A 변환은 이 버전에 포함하지 않습니다.\n\n'
            '외부 통신·자동 업데이트·사용기록 수집이 없습니다.\n'
            'OneDrive 등 자동 동기화 폴더는 저장 위치로 사용하지 마세요.\n'
            '강제 전원 종료 후 .offline-pdf- 임시폴더가 남으면 직접 삭제하세요.\n\n'
            f'버전 {__version__} · AGPL-3.0-or-later · PyMuPDF / Python Tkinter',parent=self.root)


def main():
    disable_network()
    root=tk.Tk();App(root);root.mainloop()
