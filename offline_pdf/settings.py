"""Display settings dialog. No document, path, or password history is persisted."""

from tkinter import messagebox

import customtkinter as ctk

from . import ctk_widgets as ttk
from . import theme
from .appearance import apply_theme
from .localization import apply_language, language, tr
from .preferences import save_preferences


def show_settings(app):
    if app.busy():
        return
    if getattr(app, "settings_dialog", None) and app.settings_dialog.winfo_exists():
        app.settings_dialog.lift()
        return
    dialog = ctk.CTkToplevel(app.root)
    app.settings_dialog = dialog
    dialog.title("설정")
    dialog.resizable(False, False)
    dialog.transient(app.root)
    body = ttk.Frame(dialog)
    body.pack(fill="both", expand=True, padx=24, pady=22)
    font = (theme.FONT_FAMILY, 15)
    choices = {}

    def choice_row(row, label, options, current):
        """A segmented toggle: one rounded control, the active option filled in."""
        names = {tr(text): value for text, value in options}
        ttk.Label(body, text=label, font=(theme.BOLD_FAMILY, 15, "bold")).grid(
            row=row, column=0, sticky="w", padx=(0, 24), pady=8
        )
        control = ttk.SegmentedChoice(
            body, values=names, font=font, width=260, dynamic_resizing=False
        )
        control.set(next(name for name, value in names.items() if value == current))
        control.grid(row=row, column=1, sticky="ew", pady=8)
        choices[label] = (control, names)
        return control

    dialog.language_choice = choice_row(
        0, "언어", (("한국어", "ko"), ("English", "en")), language()
    )
    dialog.theme_choice = choice_row(
        1, "테마", (("기본", "default"), ("다크모드", "dark")), app.preferences["theme"]
    )

    def selected(label):
        control, names = choices[label]
        return names[control.get()]

    def apply():
        lang, theme_name = selected("언어"), selected("테마")
        try:
            save_preferences(lang, theme_name)
        except OSError:
            messagebox.showerror(
                tr("설정"), tr("설정을 저장하지 못했습니다. 폴더 권한을 확인하세요."), parent=dialog
            )
            return
        dialog.destroy()
        app.preferences = {"language": lang, "theme": theme_name}
        apply_theme(app.root, theme_name)
        apply_language(app.root, lang)
        for card in app.cards.values():
            card.paint()
        app.file_list.draw()
        app.feedback.changed()
        app.arrange_cards(app.cards_frame.winfo_width(), force=True)

    actions = ttk.Frame(body)
    actions.grid(row=2, column=0, columnspan=2, sticky="e", pady=(22, 0))
    ttk.Button(actions, text="취소", command=dialog.destroy).pack(side="left", padx=6)
    ttk.Button(actions, text="적용", command=apply, style="Run.TButton").pack(side="left")
    dialog.update_idletasks()
    x = app.root.winfo_rootx() + (app.root.winfo_width() - dialog.winfo_width()) // 2
    y = app.root.winfo_rooty() + (app.root.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{x}+{y}")
    dialog.grab_set()
    return dialog
