"""In-memory page ordering and a virtualized, draggable Tk thumbnail grid."""
from __future__ import annotations

import base64
from collections import OrderedDict
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

import pymupdf as pdf
from .engine import UserError, open_pdf, pages
from .ui import BG, PANEL, INK, MUTED, LINE, BLUE, SOFT, FONT


class PageOrder:
    def __init__(self,count):
        self.count=count;self.serial=count;self.items=[(i+1,i,0) for i in range(count)]
        self.selected=set();self.history=[]

    def remember(self):
        self.history.append((list(self.items),set(self.selected)))
        if len(self.history)>40:self.history.pop(0)

    def move(self,ids,boundary):
        moved=[p for p in self.items if p[0] in ids]
        if not moved:return False
        boundary=max(0,min(len(self.items),boundary))
        position=sum(p[0] not in ids for p in self.items[:boundary])
        rest=[p for p in self.items if p[0] not in ids]
        result=rest[:position]+moved+rest[position:]
        if result==self.items:return False
        self.remember();self.items=result;self.selected={p[0] for p in moved};return True

    def rotate(self):
        if not self.selected:return
        self.remember();self.items=[(uid,n,(angle+90)%360) if uid in self.selected else (uid,n,angle) for uid,n,angle in self.items]

    def delete(self):
        if not self.selected:return
        if len(self.selected)==len(self.items):raise UserError('저장할 페이지를 한 장 이상 남겨 주세요.')
        self.remember();self.items=[p for p in self.items if p[0] not in self.selected];self.selected.clear()

    def reset(self):
        self.remember();self.items=[(i+1,i,0) for i in range(self.count)];self.selected.clear()

    def apply_text(self,text):
        order=pages(text,self.count,duplicates=True)
        self.remember();self.items=[]
        for n in order:self.serial+=1;self.items.append((self.serial,n,0))
        self.selected.clear()

    def undo(self):
        if self.history:self.items,self.selected=self.history.pop()

    def plan(self):return [{'page':n,'rotation':angle} for uid,n,angle in self.items]


class PageOrganizer(ttk.Frame):
    def __init__(self,master,app):
        super().__init__(master)
        self.app=app;self.doc=None;self.path=None;self.fingerprint=None;self.model=None
        self.cache=OrderedDict();self.timer=None;self.autoscroll=None;self.generation=0
        self.columns=4;self.cellw=220;self.cellh=295;self.drag=None;self.dragging=False;self.boundary=None;self.hover=None
        top=ttk.Frame(self);top.pack(fill='x',pady=(0,10))
        self.filename=ttk.Label(top,text='PDF 파일 하나를 추가하세요.',font=(FONT,11,'bold'),wraplength=480);self.filename.pack(side='left')
        ttk.Button(top,text='파일·저장 설정',command=app.organizer_settings).pack(side='right')
        ttk.Button(top,text='PDF 선택',command=app.add_files).pack(side='right',padx=7)
        self.drop_area=tk.Frame(self,bg=BG,highlightbackground=LINE,highlightthickness=2,padx=12,pady=8);self.drop_area.pack(fill='x',pady=(0,10))
        self.drop_icon=tk.Canvas(self.drop_area,bg=BG,width=40,height=35,highlightthickness=0);self.drop_icon.pack(side='left',padx=(0,10))
        self.drop_title=tk.Label(self.drop_area,text='PDF 하나를 여기에 끌어놓으세요',bg=BG,fg=INK,font=(FONT,10,'bold'));self.drop_title.pack(anchor='w')
        self.drop_sub=tk.Label(self.drop_area,text='다른 파일을 넣으면 새 문서로 바뀝니다',bg=BG,fg=MUTED,font=(FONT,9));self.drop_sub.pack(anchor='w')
        from .effects import DropHover
        self.drop_hover=DropHover(app.root,self.drop_area,self.drop_title,self.drop_sub,self.drop_icon,app.busy)
        bar=ttk.Frame(self);bar.pack(fill='x',pady=(0,8))
        self.all=tk.BooleanVar();ttk.Checkbutton(bar,text='전체 선택',variable=self.all,command=self.select_all).pack(side='left')
        self.selection_label=ttk.Label(bar,text='선택 없음',style='Muted.TLabel');self.selection_label.pack(side='left',padx=8)
        self.edit_buttons=[]
        for title,command in [('회전',self.rotate),('삭제',self.delete),('크게 보기',self.enlarge)]:
            b=ttk.Button(bar,text=title,command=command);b.pack(side='left',padx=3);self.edit_buttons.append(b)
        ttk.Button(bar,text='처음 상태로',command=self.reset).pack(side='right')
        self.undo_button=ttk.Button(bar,text='되돌리기',command=self.undo);self.undo_button.pack(side='right',padx=6)
        ttk.Label(self,text='카드를 끌어 순서를 바꾸세요. Ctrl·Shift로 여러 쪽 선택 · 더블클릭으로 크게 보기',style='Muted.TLabel').pack(anchor='w',pady=(0,10))
        area=ttk.Frame(self);area.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(area,bg=BG,highlightthickness=0,height=300,takefocus=True,yscrollincrement=35)
        self.scroll=ttk.Scrollbar(area,command=self.scroll_to);self.scroll.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True);self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<ButtonPress-1>',self.press);self.canvas.bind('<B1-Motion>',self.motion);self.canvas.bind('<ButtonRelease-1>',self.release)
        self.canvas.bind('<Double-Button-1>',self.double_click);self.canvas.bind('<Motion>',self.mouse_hover)
        self.canvas.bind('<Leave>',lambda e:self.clear_hover())
        self.canvas.bind('<MouseWheel>',self.wheel);self.canvas.bind('<Button-4>',self.wheel);self.canvas.bind('<Button-5>',self.wheel)
        self.canvas.bind('<Control-a>',lambda e:self.select_all(True));self.canvas.bind('<Delete>',lambda e:self.delete())
        self.canvas.bind('<Return>',lambda e:self.enlarge());self.canvas.bind('<Control-z>',lambda e:self.undo())
        self.canvas.bind('<Alt-Left>',lambda e:self.keyboard_move(-1));self.canvas.bind('<Alt-Right>',lambda e:self.keyboard_move(1))
        for key,delta in [('Left',-1),('Right',1),('Up',-4),('Down',4)]:self.canvas.bind('<'+key+'>',lambda e,d=delta:self.keyboard_select(d))
        self.order_label=ttk.Label(self,text='',style='Muted.TLabel',wraplength=1000);self.order_label.pack(anchor='w',pady=(10,0))
        app.root.bind('<Configure>',lambda e:self.canvas.config(height=max(220,min(550,e.height-520))) if e.widget is app.root else None,add='+')

    def close_document(self):
        self.generation+=1
        self.drag=None;self.dragging=False;self.boundary=None;self.hover=None
        for name in ('timer','autoscroll'):
            handle=getattr(self,name)
            if handle:
                try:self.after_cancel(handle)
                except tk.TclError:pass
                setattr(self,name,None)
        if self.doc:self.doc.close()
        self.doc=None;self.path=None;self.fingerprint=None;self.model=None;self.cache.clear()

    def matches(self,path):
        try:
            p=Path(path);stat=p.stat()
            return self.path==str(p.resolve()) and self.fingerprint==(stat.st_size,stat.st_mtime_ns)
        except OSError:return False

    def load(self,path,password=''):
        if path and self.doc and self.matches(path):return
        self.close_document()
        if not path:self.filename.config(text='PDF 파일 하나를 추가하세요.');self.draw();return
        try:
            self.doc,_=open_pdf(path,password)
            self.path=str(Path(path).resolve());stat=Path(path).stat();self.fingerprint=(stat.st_size,stat.st_mtime_ns)
            self.model=PageOrder(self.doc.page_count)
            self.filename.config(text=Path(path).name+' · '+str(self.doc.page_count)+'페이지')
        except (UserError,OSError) as exc:self.filename.config(text=str(exc))
        self.canvas.yview_moveto(0);self.draw()

    def scroll_to(self,*args):self.canvas.yview(*args);self.draw()
    def wheel(self,event):
        step=(-1 if event.num==4 else 1) if event.num in (4,5) else (-1 if event.delta>0 else 1)
        self.canvas.yview_scroll(step*2,'units');self.draw();return 'break'

    def draw(self):
        self.generation+=1;generation=self.generation
        if self.timer:self.after_cancel(self.timer);self.timer=None
        self.canvas.delete('all');w=max(self.canvas.winfo_width(),300)
        self.columns=max(1,min(4,int(w/210)));self.cellw=w/self.columns
        count=len(self.model.items) if self.model else 0
        total=max(120,((count+self.columns-1)//self.columns)*self.cellh)
        self.canvas.configure(scrollregion=(0,0,w,total))
        if not self.model:
            self.canvas.create_text(24,35,anchor='nw',text='PDF를 추가하면 페이지가 여기에 표시됩니다.',fill=MUTED,font=(FONT,11));self.update_summary();return
        top=self.canvas.canvasy(0);bottom=top+self.canvas.winfo_height()
        start=max(0,int(top/self.cellh)*self.columns);end=min(count,(int(bottom/self.cellh)+2)*self.columns)
        requests=[]
        for i in range(start,end):
            uid,n,angle=self.model.items[i];x=(i%self.columns)*self.cellw+7;y=(i//self.columns)*self.cellh+5
            cw=self.cellw-14;selected=uid in self.model.selected;outline=BLUE if selected or uid==self.hover else LINE
            self.canvas.create_rectangle(x,y,x+cw,y+280,fill=SOFT if selected else PANEL,outline=outline,width=2 if selected else 1)
            self.canvas.create_text(x+12,y+15,anchor='w',text=f'저장 {i+1}번째',fill=BLUE if selected else MUTED,font=(FONT,9))
            self.canvas.create_text(x+cw-15,y+15,text='⠿',fill=MUTED,font=(FONT,13))
            self.canvas.create_rectangle(x+12,y+32,x+cw-12,y+238,fill=BG,outline='')
            self.canvas.create_text(x+12,y+260,anchor='w',text=('☑' if selected else '□')+f' 원본 {n+1}쪽'+(f' · {angle}°' if angle else ''),font=(FONT,10),fill=INK)
            key=(n,angle,int(cw-38))
            if key in self.cache:
                self.cache.move_to_end(key);self.canvas.create_image(x+cw/2,y+135,image=self.cache[key])
            else:requests.append((key,n,angle,x+cw/2,y+135,cw-38))
        if self.boundary is not None:
            b=self.boundary;col=b%self.columns;row=b//self.columns
            if b==count and col==0 and b:col=self.columns;row-=1
            x=col*self.cellw+1;y=row*self.cellh+5
            self.canvas.create_line(x,y,x,y+280,fill=BLUE,width=4)
        self.update_summary()
        def thumbnail():
            self.timer=None
            if generation!=self.generation or not self.doc or not requests:return
            key,n,angle,x,y,width=requests.pop(0)
            try:
                page=self.doc[n];rect=page.rect
                rw,rh=(rect.height,rect.width) if angle%180 else (rect.width,rect.height)
                scale=min(width/rw,195/rh)
                pix=page.get_pixmap(matrix=pdf.Matrix(scale,scale).prerotate(angle),alpha=False,colorspace=pdf.csRGB)
                photo=tk.PhotoImage(data=base64.b64encode(pix.tobytes('png')))
                self.cache[key]=photo
                while len(self.cache)>64:self.cache.popitem(last=False)
                self.canvas.create_image(x,y,image=photo)
            except Exception:self.canvas.create_text(x,y,text=f'{n+1}쪽',fill=MUTED,font=(FONT,11))
            if requests:self.timer=self.after(5,thumbnail)
        if requests:self.timer=self.after(1,thumbnail)

    def update_summary(self):
        m=self.model;count=len(m.items) if m else 0;selected=len(m.selected) if m else 0
        self.selection_label.config(text=f'{selected}페이지 선택' if selected else '선택 없음')
        self.all.set(bool(count and selected==count))
        for b in self.edit_buttons:b.config(state='normal' if selected and not self.app.busy() else 'disabled')
        self.undo_button.config(state='normal' if m and m.history and not self.app.busy() else 'disabled')
        self.order_label.config(text='저장 순서 · 원본 쪽 번호  '+ ' → '.join(str(p[1]+1) for p in m.items[:30])+(' …' if count>30 else '') if m else '')
        if self.app.tool=='extract':self.app.summary.set(f'{count}페이지를 저장합니다' if m else 'PDF 파일 하나를 추가해 주세요.')

    def hit(self,x,y):
        if not self.model:return None
        col=int(x/self.cellw);row=int(self.canvas.canvasy(y)/self.cellh);i=row*self.columns+col
        return i if 0<=col<self.columns and 0<=i<len(self.model.items) else None

    def press(self,event):
        if self.app.busy() or not self.model:return
        self.canvas.focus_set();i=self.hit(event.x,event.y)
        if i is None:return
        uid=self.model.items[i][0];ctrl=event.state&0x0004;shift=event.state&0x0001
        checkbox=self.canvas.canvasy(event.y)%self.cellh>242 and event.x%self.cellw<45
        if ctrl or checkbox:
            if uid in self.model.selected:self.model.selected.remove(uid)
            else:self.model.selected.add(uid)
        elif shift and self.model.selected:
            anchor=next((j for j,p in enumerate(self.model.items) if p[0] in self.model.selected),i)
            self.model.selected.update(p[0] for p in self.model.items[min(i,anchor):max(i,anchor)+1])
        elif uid not in self.model.selected:self.model.selected={uid}
        self.drag=(event.x,event.y,uid,bool(ctrl or shift or checkbox));self.dragging=False;self.draw()

    def motion(self,event):
        if self.app.busy() or not self.drag:return
        x,y,uid,modified=self.drag
        if abs(event.x-x)+abs(event.y-y)>6:self.dragging=True
        if not self.dragging:return
        self.last_pointer=(event.x,event.y);i=self.hit(event.x,event.y)
        self.boundary=(i+(event.x%self.cellw>self.cellw/2)) if i is not None else len(self.model.items)
        self.draw()
        if self.autoscroll is None:self.autoscroll=self.after(60,self.auto_scroll)

    def auto_scroll(self):
        self.autoscroll=None
        if not self.dragging or not self.drag:return
        x,y=self.last_pointer;height=self.canvas.winfo_height()
        if y<35 or y>height-35:
            self.canvas.yview_scroll(-1 if y<35 else 1,'units')
            i=self.hit(x,y);self.boundary=i+(x%self.cellw>self.cellw/2) if i is not None else len(self.model.items);self.draw()
        self.autoscroll=self.after(60,self.auto_scroll)

    def release(self,event):
        if not self.drag:return
        if not self.app.busy():
            if self.dragging and self.boundary is not None:self.model.move(self.model.selected,self.boundary)
            elif not self.drag[3]:self.model.selected={self.drag[2]}
        self.drag=None;self.dragging=False;self.boundary=None
        if self.autoscroll:self.after_cancel(self.autoscroll);self.autoscroll=None
        self.draw()

    def mouse_hover(self,event):
        i=self.hit(event.x,event.y);uid=self.model.items[i][0] if i is not None else None
        if uid!=self.hover:self.hover=uid;self.draw()
    def clear_hover(self):
        if self.hover is not None:self.hover=None;self.draw()
    def double_click(self,event):
        i=self.hit(event.x,event.y)
        if i is not None and not self.app.busy():self.model.selected={self.model.items[i][0]};self.enlarge()
    def select_all(self,force=None):
        if self.model and not self.app.busy():
            self.model.selected={p[0] for p in self.model.items} if force is True or self.all.get() else set();self.draw()
        return 'break'
    def rotate(self):
        if self.model and not self.app.busy():self.model.rotate();self.draw()
    def delete(self):
        if self.model and not self.app.busy():
            try:self.model.delete()
            except UserError as exc:messagebox.showinfo('페이지 삭제',str(exc),parent=self.app.root)
            self.draw()
    def undo(self):
        if self.model and not self.app.busy():self.model.undo();self.draw()
    def reset(self):
        if self.model and not self.app.busy():self.model.reset();self.draw()
    def apply_text(self):
        if not self.model or self.app.busy():return
        value=simpledialog.askstring('페이지 번호로 지정','예: 3,1,2 / 1-3,5 / 같은 쪽 반복: 1,1,2',parent=self.app.root)
        if value is None:return
        try:self.model.apply_text(value)
        except UserError as exc:messagebox.showinfo('페이지 지정',str(exc),parent=self.app.root)
        self.draw()
    def keyboard_move(self,delta):
        if self.model and self.model.selected and not self.app.busy():
            positions=[i for i,p in enumerate(self.model.items) if p[0] in self.model.selected]
            boundary=max(0,min(positions)-1) if delta<0 else min(len(self.model.items),max(positions)+2)
            self.model.move(self.model.selected,boundary);self.draw()
        return 'break'
    def keyboard_select(self,delta):
        if self.model and not self.app.busy():
            i=next((j for j,p in enumerate(self.model.items) if p[0] in self.model.selected),0)
            if abs(delta)==4:delta=self.columns*(1 if delta>0 else -1)
            i=max(0,min(len(self.model.items)-1,i+delta));self.model.selected={self.model.items[i][0]}
            self.canvas.yview_moveto(max(0,(i//self.columns)*self.cellh)/max(1,float(self.canvas.cget('scrollregion').split()[-1])));self.draw()
        return 'break'
    def enlarge(self):
        if not self.model or self.app.busy():return
        item=next((p for p in self.model.items if p[0] in self.model.selected),self.model.items[0])
        self.app.page_index=item[1];self.app.organizer_preview_uid=item[0];self.app.show_preview()
