"""Small Tk-thread hover transitions; no native callback calls into Tcl."""
import time
import tkinter as tk
from .ui import BG, BLUE, SOFT, LINE, INK, MUTED, icon


def mix(a,b,t):
    return '#'+''.join(f'{round(int(a[i:i+2],16)*(1-t)+int(b[i:i+2],16)*t):02x}' for i in (1,3,5))


class Tween:
    def __init__(self,widget,paint):self.widget=widget;self.paint=paint;self.value=0.;self.timer=None
    def to(self,target):
        if self.timer:self.widget.after_cancel(self.timer);self.timer=None
        start=self.value;began=time.monotonic()
        def tick():
            self.timer=None
            if not self.widget.winfo_exists():return
            t=min(1,(time.monotonic()-began)/.16);eased=1-(1-t)**3
            self.value=start+(target-start)*eased;self.paint(self.value)
            if t<1:self.timer=self.widget.after(16,tick)
        tick()
    def close(self):
        if self.timer:
            try:self.widget.after_cancel(self.timer)
            except tk.TclError:pass
            self.timer=None


class DropHover:
    """Polling works even while Explorer's drag loop suppresses Tk Enter events."""
    def __init__(self,root,area,title,sub,logo,busy):
        self.root=root;self.area=area;self.title=title;self.sub=sub;self.logo=logo;self.busy=busy;self.active=False;self.timer=None;self.closed=False
        self.tween=Tween(area,self.paint);self.poll()
    def paint(self,value):
        color=mix(BG,SOFT,value);self.area.configure(bg=color,highlightbackground=mix(LINE,BLUE,value))
        self.title.configure(bg=color,fg=mix(INK,BLUE,value));self.sub.configure(bg=color,fg=MUTED)
        self.logo.configure(bg=color);self.logo.delete('all');icon(self.logo,'upload',8,8-round(value*4),mix(MUTED,BLUE,value))
    def poll(self):
        self.timer=None
        if self.closed:return
        active=False
        if self.area.winfo_ismapped() and not self.busy():
            x,y=self.root.winfo_pointerxy();w=self.root.winfo_containing(x,y)
            active=bool(w and (str(w)==str(self.area) or str(w).startswith(str(self.area)+'.')))
        if active!=self.active:self.active=active;self.tween.to(1 if active else 0)
        self.timer=self.root.after(60,self.poll)
    def close(self):
        self.closed=True;self.tween.close()
        if self.timer:
            try:self.root.after_cancel(self.timer)
            except tk.TclError:pass
            self.timer=None
