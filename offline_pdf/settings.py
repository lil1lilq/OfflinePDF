"""Display settings dialog. No document, path, or password history is persisted."""

import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk

from . import ctk_widgets as ttk
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
    body = ttk.Frame(dialog, padding=24)
    body.pack(fill="both", expand=True)
    selected_language = tk.StringVar(dialog, value=language())
    selected_theme = tk.StringVar(dialog, value=app.preferences["theme"])
    ttk.Label(body, text="언어").grid(row=0, column=0, sticky="w", padx=(0, 28), pady=10)
    ttk.Radiobutton(
        body, text="한국어", style="Settings.TRadiobutton", variable=selected_language, value="ko"
    ).grid(row=0, column=1, sticky="w", padx=8)
    ttk.Radiobutton(
        body, text="English", style="Settings.TRadiobutton", variable=selected_language, value="en"
    ).grid(row=0, column=2, sticky="w", padx=8)
    ttk.Label(body, text="테마").grid(row=1, column=0, sticky="w", padx=(0, 28), pady=10)
    ttk.Radiobutton(
        body, text="기본", style="Settings.TRadiobutton", variable=selected_theme, value="default"
    ).grid(row=1, column=1, sticky="w", padx=8)
    ttk.Radiobutton(
        body, text="다크모드", style="Settings.TRadiobutton", variable=selected_theme, value="dark"
    ).grid(row=1, column=2, sticky="w", padx=8)

    def apply():
        lang, theme = selected_language.get(), selected_theme.get()
        try:
            save_preferences(lang, theme)
        except OSError:
            messagebox.showerror(
                tr("설정"), tr("설정을 저장하지 못했습니다. 폴더 권한을 확인하세요."), parent=dialog
            )
            return
        dialog.destroy()
        app.preferences = {"language": lang, "theme": theme}
        apply_theme(app.root, theme)
        apply_language(app.root, lang)
        for card in app.cards.values():
            card.paint()
        app.file_list.draw()
        app.feedback.changed()
        app.arrange_cards(app.cards_frame.winfo_width(), force=True)

    actions = ttk.Frame(body)
    actions.grid(row=2, column=0, columnspan=3, sticky="e", pady=(22, 0))
    ttk.Button(actions, text="취소", command=dialog.destroy).pack(side="left", padx=6)
    ttk.Button(actions, text="적용", command=apply).pack(side="left")
    dialog.update_idletasks()
    x = app.root.winfo_rootx() + (app.root.winfo_width() - dialog.winfo_width()) // 2
    y = app.root.winfo_rooty() + (app.root.winfo_height() - dialog.winfo_height()) // 2
    dialog.geometry(f"+{x}+{y}")
    dialog.grab_set()
    return dialog
