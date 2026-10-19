"""Shared sidebar, compact tools, fixed actions and one document viewport."""

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from . import __version__
from .ui import (
    BG,
    BLUE,
    CARD_TEXT,
    FONT,
    INK,
    LINE,
    MUTED,
    PANEL,
    SOFT,
    ScrollPane,
    ToolCard,
    icon,
    setup_style,
)
from .workspace import FileList, StatusFeedback, WindowDropHover


def panel(master):
    return tk.Frame(master, bg=PANEL, highlightbackground=LINE, highlightthickness=1)


def build(app):
    root = app.root
    root.title(f"OfflinePDF {__version__}")
    root.geometry("1280x800")
    root.minsize(900, 620)
    root.configure(bg=BG)
    root.option_add("*Font", (FONT, 10))
    setup_style(root)
    app.auto_open = tk.BooleanVar(value=True)
    header = tk.Frame(root, bg=PANEL, padx=20, pady=9)
    header.pack(fill="x")
    logo = tk.Canvas(header, width=32, height=32, bg=BLUE, highlightthickness=0)
    logo.pack(side="left", padx=(0, 10))
    icon(logo, "merge", 4, 4, PANEL)
    tk.Label(header, text="OfflinePDF", bg=PANEL, fg=INK, font=(FONT, 16, "bold")).pack(side="left")
    tk.Label(header, text=__version__, bg=PANEL, fg=MUTED, font=(FONT, 9)).pack(side="left", padx=9)
    app.home_button = ttk.Button(header, text="뒤로가기", command=app.go_back, style="Back.TButton")
    app.home_button.pack(side="right")
    app.header_task = ttk.Frame(header, style="Panel.TFrame")
    app.header_task.pack(side="left", fill="x", expand=True, padx=(30, 16))
    status_box = tk.Frame(root, bg=PANEL, height=43)
    status_box.pack(side="bottom", fill="x")
    status_box.pack_propagate(False)
    app.status = tk.StringVar(value="파일을 추가하거나 작업할 도구를 선택하세요.")
    ttk.Button(status_box, text="도움말", command=app.help).pack(side="right", padx=8, pady=4)
    status = tk.Label(status_box, text="", anchor="w", bg=PANEL, fg=MUTED, font=(FONT, 9), padx=16)
    status.pack(fill="both", expand=True)
    status.bind("<Configure>", lambda e: status.configure(wraplength=max(300, e.width - 30)))
    app.feedback = StatusFeedback(app, status)
    app.feedback.changed()
    app.host = tk.Frame(root, bg=BG, highlightthickness=1, highlightbackground=LINE)
    app.host.pack(fill="both", expand=True)
    app.sidebar = tk.Frame(app.host, bg=PANEL, width=224, padx=12, pady=14)
    app.sidebar.pack(side="left", fill="y")
    app.sidebar.pack_propagate(False)
    app.file_count = tk.Label(
        app.sidebar, text="작업 파일  0개", bg=PANEL, fg=INK, font=(FONT, 10, "bold")
    )
    app.file_count.pack(anchor="w", pady=(0, 8))
    app.add_button = ttk.Button(app.sidebar, text="＋  파일 추가", command=app.add_files)
    app.add_button.pack(fill="x", pady=(0, 10))
    controls = tk.Frame(app.sidebar, bg=PANEL)
    controls.pack(side="bottom", fill="x", pady=(9, 0))
    app.sidebar_total = tk.StringVar(value="파일 없음")
    tk.Label(
        controls,
        textvariable=app.sidebar_total,
        bg=PANEL,
        fg=MUTED,
        font=(FONT, 9),
        wraplength=195,
        anchor="w",
    ).pack(fill="x", pady=(0, 8))
    order = tk.Frame(controls, bg=PANEL)
    order.pack(fill="x")
    for text, command in [
        ("↑", lambda: app.move(-1)),
        ("↓", lambda: app.move(1)),
        ("선택 제거", app.remove_files),
    ]:
        ttk.Button(order, text=text, command=command, width=3 if len(text) == 1 else 8).pack(
            side="left", padx=(0, 3)
        )
    ttk.Button(controls, text="전체 비우기", command=app.clear_files).pack(fill="x", pady=(6, 0))
    ttk.Checkbutton(controls, text="완료 후 폴더 열기", variable=app.auto_open).pack(
        anchor="w", pady=(8, 0)
    )
    filebox = tk.Frame(app.sidebar, bg=PANEL)
    filebox.pack(fill="both", expand=True)
    app.file_list = FileList(filebox, app)
    app.file_list.pack(side="left", fill="both", expand=True)
    fs = ttk.Scrollbar(filebox, command=app.file_list.yview)
    fs.pack(side="right", fill="y")
    app.file_scroll = fs

    def sidebar_scroll(first, last):
        fs.set(first, last)
        overflow = float(first) > 0.00001 or float(last) < 0.99999
        if overflow and not fs.winfo_manager():
            fs.pack(side="right", fill="y")
        elif not overflow and fs.winfo_manager():
            fs.pack_forget()

    app.file_list.configure(yscrollcommand=sidebar_scroll)
    app.file_list.bind("<<ListboxSelect>>", app.file_selected)
    app.file_list.bind("<Delete>", lambda e: app.remove_files())
    app.content_host = ttk.Frame(app.host)
    app.content_host.pack(side="left", fill="both", expand=True)
    app.home = ScrollPane(app.content_host)
    app.home.pack(fill="both", expand=True)
    home = ttk.Frame(app.home.inner, padding=(22, 20, 22, 15))
    home.pack(fill="both", expand=True)
    app.home_title = ttk.Label(home, text="어떤 작업을 할까요?", style="Title.TLabel")
    app.home_title.pack(anchor="w")
    app.home_description = ttk.Label(
        home,
        text="왼쪽에서 파일을 확인하고 필요한 도구를 선택하세요.",
        style="Muted.TLabel",
        wraplength=800,
    )
    app.home_description.pack(anchor="w", pady=(4, 12))
    app.chain_cancel_button = ttk.Button(home, text="이어서 작업 취소", command=app.cancel_continue)
    row = ttk.Frame(home)
    row.pack(fill="x", pady=(0, 9))
    app.home_section = ttk.Label(row, text="자주 쓰는 도구", font=(FONT, 10, "bold"))
    app.home_section.pack(side="left")
    app.all_tools_button = ttk.Button(
        row, text="전체 도구 보기  ⌄", style="Quiet.TButton", command=app.toggle_tools
    )
    app.all_tools_button.pack(side="right")
    app.cards_frame = ttk.Frame(home)
    app.cards_frame.pack(fill="x")
    app.cards = {key: ToolCard(app.cards_frame, key, app.select_tool) for key in CARD_TEXT}
    app.show_all_tools = False
    app.card_columns = 0
    app.card_layout = None
    app.card_resize_timer = None
    app.cards_frame.bind("<Configure>", lambda event: app.arrange_cards(event.width))
    app.home.canvas.bind("<Configure>", lambda event: app.schedule_cards(), add="+")
    app.work = ttk.Frame(app.content_host)
    footer = ttk.Frame(app.work, padding=(18, 8))
    footer.pack(side="bottom", fill="x")
    app.summary = tk.StringVar(value="파일을 추가해 주세요.")
    actions = ttk.Frame(footer)
    actions.pack(fill="x")
    app.run_button = ttk.Button(
        actions, text="병합  →", style="Run.TButton", command=app.run, state="disabled"
    )
    app.run_button.pack(side="right")
    app.cancel_button = ttk.Button(
        actions, text="작업 취소", command=app.cancel_job, state="disabled"
    )
    app.result_actions = ttk.Frame(footer)
    app.next_button = ttk.Button(
        app.result_actions,
        text="결과로 다음 작업  →",
        command=app.continue_with_result,
        state="disabled",
    )
    app.next_button.pack(side="right")
    app.open_button = ttk.Button(
        app.result_actions, text="결과 폴더 열기", command=app.open_result, state="disabled"
    )
    app.open_button.pack(side="right", padx=(0, 8))
    app.progress = ttk.Progressbar(footer, mode="determinate")
    app.body = ttk.Frame(app.work, padding=(18, 12, 18, 4))
    app.body.pack(fill="both", expand=True)
    title_row = ttk.Frame(app.header_task, style="Panel.TFrame")
    app.task_title_row = title_row
    title_row.pack(fill="x")
    app.task_icon = tk.Canvas(title_row, width=38, height=38, bg=SOFT, highlightthickness=0)
    app.task_icon.pack(side="left", padx=(0, 10))
    title_text = ttk.Frame(title_row, style="Panel.TFrame")
    title_text.pack(side="left", fill="x", expand=True)
    app.title = ttk.Label(title_text, text="", style="Panel.TLabel", font=(FONT, 11, "bold"))
    app.title.pack(anchor="w")
    app.description = ttk.Label(title_text, text="", style="PanelMuted.TLabel", wraplength=660)
    app.description.pack(anchor="w", pady=(2, 0))
    title_text.bind(
        "<Configure>", lambda e: app.description.configure(wraplength=max(200, e.width))
    )
    app.save_bar = ttk.Frame(actions)
    app.save_bar.pack(side="left", fill="x", expand=True, padx=(0, 10))
    app.save_mode = tk.StringVar(value="원본 파일과 같은 폴더")
    app.save_mode_combo = ttk.Combobox(
        app.save_bar,
        textvariable=app.save_mode,
        values=("원본 파일과 같은 폴더", "지정한 폴더"),
        state="readonly",
        width=19,
    )
    app.save_mode_combo.pack(side="left")
    app.save_mode_combo.bind("<<ComboboxSelected>>", app.change_save_mode)
    home_dir = Path.home()
    default = home_dir / "Documents" if (home_dir / "Documents").is_dir() else home_dir
    app.output = tk.StringVar(value=str(default))
    app.output_entry = ttk.Entry(app.save_bar, textvariable=app.output, width=20)
    app.output_entry.pack(side="left", fill="x", expand=True, padx=6)
    app.output_entry.bind("<KeyRelease>", lambda e: app.save_mode.set("지정한 폴더"))
    ttk.Button(app.save_bar, text="저장 폴더", command=app.choose_output).pack(side="left")
    app.columns = ttk.Frame(app.body)
    settings = panel(app.columns)
    settings.configure(padx=12, pady=8)
    settings.pack(fill="x")
    app.form = ttk.Frame(settings, style="Panel.TFrame")
    app.form.pack(fill="x")
    app.form_cells = []
    app.form_columns = 0
    app.form.bind("<Configure>", lambda e: app.arrange_fields(e.width))
    app.name_frame = ttk.Frame(settings, style="Panel.TFrame")
    ttk.Label(app.name_frame, text="저장 파일 이름", style="Panel.TLabel").pack(
        side="left", padx=(0, 8)
    )
    app.output_name = tk.StringVar(value="합친문서.pdf")
    ttk.Entry(app.name_frame, textvariable=app.output_name, width=27).pack(
        side="left", fill="x", expand=True
    )
    app.output_password_button = ttk.Button(
        app.name_frame, text="암호 추가", command=app.set_output_password
    )
    app.output_password_button.pack(side="left", padx=(8, 0))
    app.security = ttk.Label(settings, text="", style="PanelMuted.TLabel", wraplength=800)
    app.region_controls = ttk.Frame(settings, style="Panel.TFrame")
    ttk.Button(
        app.region_controls, text="현재 페이지 삭제 영역 지우기", command=app.clear_regions
    ).pack(side="left")
    app.region_status = ttk.Label(
        app.region_controls, text="삭제 영역 0개", style="PanelMuted.TLabel"
    )
    app.region_status.pack(side="left", padx=8)
    app.split_summary = ttk.Label(settings, text="", style="PanelMuted.TLabel", wraplength=800)
    workspace = ttk.Frame(app.body)
    app.document_host = workspace
    workspace.pack(fill="both", expand=True, pady=(8, 0))
    app.file_overview = tk.Frame(workspace, bg=BG)
    overview_header = ttk.Frame(app.file_overview)
    overview_header.pack(fill="x", pady=(4, 6))
    app.overview_title = ttk.Label(
        overview_header, text="", font=(FONT, 12, "bold"), width=1, wraplength=450
    )
    app.overview_title.pack(side="left", fill="x", expand=True)
    app.overview_title.bind(
        "<Configure>", lambda e: app.overview_title.configure(wraplength=max(80, e.width))
    )
    app.overview_detail = ttk.Label(
        app.file_overview, text="", style="Muted.TLabel", wraplength=700
    )
    app.overview_detail.pack(anchor="w", pady=(0, 12))
    app.preview_button = ttk.Button(
        overview_header, text="크게 미리보기", command=app.toggle_preview
    )
    app.preview_button.pack(side="right")
    app.ai_preview_button = ttk.Button(
        overview_header, text="AI 비교 미리보기", command=lambda: app.run(preview=True)
    )
    overview_area = ttk.Frame(app.file_overview)
    overview_area.pack(fill="both", expand=True, pady=(10, 0))
    app.overview_canvas = tk.Canvas(overview_area, bg=BG, highlightthickness=0, height=120)
    app.overview_canvas.own_wheel = True
    overview_scroll = ttk.Scrollbar(overview_area, command=app.overview_canvas.yview)
    overview_scroll.pack(side="right", fill="y")
    app.overview_canvas.configure(yscrollcommand=overview_scroll.set)
    app.overview_canvas.pack(fill="both", expand=True)
    app.overview_canvas.bind(
        "<MouseWheel>",
        lambda e: app.overview_canvas.yview_scroll(-2 if e.delta > 0 else 2, "units"),
    )
    app.overview_canvas.bind("<Configure>", lambda e: app.schedule_preview())
    from .organizer import PageOrganizer

    app.organizer = PageOrganizer(workspace, app)
    preview = panel(workspace)
    app.preview_panel = preview
    nav = ttk.Frame(preview, style="Panel.TFrame", padding=(10, 7))
    nav.pack(fill="x")
    ttk.Label(nav, text="미리보기", style="Panel.TLabel").pack(side="left")
    ttk.Button(nav, text="다음 ›", command=lambda: app.turn(1)).pack(side="right")
    app.page_label = ttk.Label(nav, text="미리보기", style="PanelMuted.TLabel")
    app.page_label.pack(side="right", padx=8)
    ttk.Button(nav, text="‹ 이전", command=lambda: app.turn(-1)).pack(side="right")
    zoom = ttk.Frame(preview, style="Panel.TFrame", padding=(10, 0, 10, 6))
    app.preview_zoom_row = zoom
    zoom.pack(fill="x")
    for text, command in [
        ("폭 맞춤", lambda: app.set_preview_mode("width")),
        ("한 페이지", lambda: app.set_preview_mode("page")),
        ("－", lambda: app.zoom_preview(-0.25)),
        ("＋", lambda: app.zoom_preview(0.25)),
    ]:
        ttk.Button(zoom, text=text, command=command).pack(side="left", padx=(0, 4))
    app.zoom_label = ttk.Label(zoom, text="폭 맞춤", style="PanelMuted.TLabel")
    app.zoom_label.pack(side="left", padx=4)
    app.clear_preview_regions = ttk.Button(zoom, text="영역 지우기", command=app.clear_regions)
    area = tk.Frame(preview, bg=PANEL)
    area.pack(fill="both", expand=True, padx=8, pady=(0, 8))
    app.canvas = tk.Canvas(area, bg="#e9edf4", highlightthickness=0, height=180, takefocus=True)
    app.canvas.own_wheel = True
    vs = ttk.Scrollbar(area, command=app.canvas.yview)
    vs.pack(side="right", fill="y")
    app.canvas.configure(yscrollcommand=vs.set)
    app.canvas.pack(fill="both", expand=True)
    app.canvas.bind("<Configure>", lambda e: app.schedule_preview())
    for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
        app.canvas.bind(sequence, app.preview_wheel)
    app.preview_hscroll = ttk.Scrollbar(preview, orient="horizontal", command=app.canvas.xview)
    app.preview_hscroll.pack(fill="x", padx=8, pady=(0, 5))
    app.canvas.configure(xscrollcommand=app.preview_hscroll.set)
    app.canvas.bind("<ButtonPress-1>", app.draw_start)
    app.canvas.bind("<B1-Motion>", app.draw_move)
    app.canvas.bind("<ButtonRelease-1>", app.draw_end)
    app.preview_timer = None
    app.window_drop_hover = WindowDropHover(app)
    app.arrange_cards(950, force=True)
    root.bind("<Configure>", lambda e: app.schedule_cards() if e.widget is root else None, add="+")
