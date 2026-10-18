"""Shared sidebar and fixed-height feedback for the desktop workspace."""
from pathlib import Path
import time
import tkinter as tk
from tkinter import font as tkfont
from .ui import BG, PANEL, INK, MUTED, LINE, BLUE, SOFT, FONT, RED
from .effects import mix, Tween


class FileList(tk.Canvas):
    """File rows with Listbox-compatible selection methods and visible metadata."""
    own_wheel = True
    def __init__(self, master, app):
        super().__init__(master, bg=PANEL, highlightthickness=0, width=190, height=150, takefocus=True)
        self.app=app;self.rows=[];self.selection=set();self.row_height=72;self.timer=None;self.flash_rows=set();self.flash_value=0.
        self.bind('<Configure>',lambda e:self.draw())
        self.bind('<Button-1>',self.click)
        self.bind('<MouseWheel>',self.wheel);self.bind('<Button-4>',self.wheel);self.bind('<Button-5>',self.wheel)
        self.bind('<Up>',lambda e:self.key(-1));self.bind('<Down>',lambda e:self.key(1))
        self.name_font=tkfont.Font(family=FONT,size=9,weight='bold')
    def insert(self,index,text):self.rows.append((str(text),'',None));self.draw()
    def delete(self,first,last=None):
        if last=='end':self.rows=[];self.selection.clear()
        elif self.rows:self.rows.pop(int(first));self.selection.clear()
        self.draw()
    def size(self):return len(self.rows)
    def get(self,index):return self.rows[int(index)][0]
    def curselection(self):return tuple(sorted(self.selection))
    def selection_clear(self,first,last=None):self.selection.clear();self.draw()
    def selection_set(self,first,last=None):
        if self.rows:
            end=len(self.rows)-1 if last=='end' else int(last) if last is not None else int(first)
            self.selection.update(range(max(0,int(first)),min(len(self.rows)-1,end)+1));self.draw()
    def set_files(self,files,metadata):
        self.rows=[(Path(path).name,metadata(path),path) for path in files]
        self.selection={i for i in self.selection if i<len(self.rows)}
        if self.rows and not self.selection:self.selection={0}
        self.draw()
    def click(self,event):
        if self.app.busy():return
        self.focus_set();index=int(self.canvasy(event.y)//self.row_height)
        if index>=len(self.rows):return
        if event.state&4:
            if index in self.selection:self.selection.remove(index)
            else:self.selection.add(index)
        elif event.state&1 and self.selection:
            self.selection.update(range(min(self.selection),index+1) if index>=min(self.selection) else range(index,max(self.selection)+1))
        else:self.selection={index}
        self.draw();self.event_generate('<<ListboxSelect>>')
    def key(self,delta):
        if self.app.busy():return 'break'
        index=max(0,min(len(self.rows)-1,(min(self.selection) if self.selection else 0)+delta))
        self.selection={index} if self.rows else set();self.draw();self.event_generate('<<ListboxSelect>>');return 'break'
    def wheel(self,event):
        step=(-1 if event.num==4 else 1) if event.num in (4,5) else (-1 if event.delta>0 else 1)
        self.yview_scroll(step,'units');return 'break'
    def draw(self):
        self.delete_items();w=max(150,self.winfo_width())
        self.configure(scrollregion=(0,0,w,len(self.rows)*self.row_height),yscrollincrement=24)
        for i,(name,meta,path) in enumerate(self.rows):
            full_name=name
            while name and self.name_font.measure(name)>2*(w-25)-24:name=name[:-1]
            if name!=full_name:name+='…'
            meta=meta.replace('이 도구에서 사용 불가','사용 불가')
            y=i*self.row_height;selected=i in self.selection
            fill=mix(PANEL,SOFT,self.flash_value) if i in self.flash_rows else SOFT if selected else BG
            self.create_rectangle(3,y+2,w-3,y+self.row_height-5,fill=fill,outline=BLUE if selected else LINE,width=1)
            self.create_text(12,y+13,anchor='nw',text=name,width=w-25,font=(FONT,9,'bold'),fill=INK)
            self.create_text(12,y+52,anchor='w',text=meta,width=w-25,font=(FONT,8),fill=MUTED)
    def delete_items(self):super().delete('all')
    def flash(self,indices):
        if self.timer:self.after_cancel(self.timer)
        self.flash_rows=set(indices);start=time.monotonic()
        def tick():
            self.timer=None
            if not self.winfo_exists():return
            self.flash_value=max(0,1-(time.monotonic()-start)/1.1);self.draw()
            if self.flash_value:self.timer=self.after(25,tick)
            else:self.flash_rows.clear()
        tick()
    def close(self):
        if self.timer:self.after_cancel(self.timer);self.timer=None


class StatusFeedback:
    def __init__(self,app,label):
        self.app=app;self.label=label;self.timer=None;self.serial=0;self.count_timer=None
        self.trace=app.status.trace_add('write',self.changed)
    def changed(self,*_):
        self.serial+=1
        text=self.app.status.get()
        warning=any(word in text for word in ('제외','0개 추가','선택하세요','불가'))
        error=any(word in text for word in ('실패','못했','오류'))
        color=RED if error else '#965b18' if warning else BLUE
        fill='#fdeced' if error else '#fff0da' if warning else SOFT
        mark='!  ' if warning or error else '↻  ' if self.app.busy() else '✓  '
        self.label.config(text=mark+text,fg=color)
        if self.timer:self.label.after_cancel(self.timer)
        start=time.monotonic()
        def tick():
            self.timer=None
            if not self.label.winfo_exists():return
            t=min(1,(time.monotonic()-start)/.9)
            bg=mix(fill,PANEL,t);self.label.config(bg=bg);self.label.master.config(bg=bg)
            if t<1:self.timer=self.label.after(25,tick)
        tick()
    def file_added(self,indices):
        self.app.file_list.flash(indices)
        if self.count_timer:self.label.after_cancel(self.count_timer)
        self.app.file_count.config(foreground=BLUE)
        self.count_timer=self.label.after(1100,self.end_count)
    def end_count(self):self.count_timer=None;self.app.file_count.config(foreground=INK)
    def close(self):
        self.app.status.trace_remove('write',self.trace)
        for timer in (self.timer,self.count_timer):
            if timer:
                try:self.label.after_cancel(timer)
                except tk.TclError:pass


class WindowDropHover:
    """Animate the application border when a pointer enters its drop surface."""
    def __init__(self,app):
        self.app=app;self.active=False;self.timer=None;self.closed=False
        self.tween=Tween(app.host,lambda value:app.host.config(highlightbackground=mix(LINE,BLUE,value)));self.poll()
    def poll(self):
        if self.closed:return
        x,y=self.app.root.winfo_pointerxy();widget=self.app.root.winfo_containing(x,y)
        active=bool(widget and not self.app.busy())
        if active!=self.active:
            self.active=active;self.tween.to(1 if active else 0)
        self.timer=self.app.root.after(70,self.poll)
    def close(self):
        self.closed=True;self.tween.close()
        if self.timer:self.app.root.after_cancel(self.timer)
