"""Appearance tokens and optional bundled desktop font."""

from __future__ import annotations

import ctypes
import sys
import tkinter.font as tkfont
from pathlib import Path

import customtkinter as ctk


def avoid_native_titlebar_updates():
    """Skip CustomTkinter's reentrant native Windows title bar color hook."""
    # CustomTkinter 5.2.2 calls Tk update() during window construction. That
    # path has caused access violations on Windows, including after modals.
    # The OS title bar stays in its normal color; application themes still work.
    ctk.CTk._deactivate_windows_window_header_manipulation = True
    ctk.CTkToplevel._deactivate_windows_window_header_manipulation = True


PALETTES = {
    "default": {
        "BG": "#f4f6fa",
        "PANEL": "#ffffff",
        "INK": "#111827",
        "MUTED": "#374151",
        "RED": "#b3384a",
        "LINE": "#dfe5ef",
        "BLUE": "#3759da",
        "SOFT": "#eaf0ff",
        "conversion": ("#f0edff", "#6954b8"),
        "page": ("#eaf0fd", "#355db4"),
        "content": ("#fcf0e8", "#99572f"),
        "security": ("#e8f5ef", "#2e7660"),
        "ai": ("#f9ecf2", "#9b506e"),
    },
    "dark": {
        "BG": "#171c25",
        "PANEL": "#222a36",
        "INK": "#f8fafc",
        "MUTED": "#d5dce6",
        "RED": "#ff929e",
        "LINE": "#394557",
        "BLUE": "#a9bcff",
        "SOFT": "#303b53",
        "conversion": ("#34304a", "#c8b9ff"),
        "page": ("#293a58", "#b5c9ff"),
        "content": ("#4a342c", "#f4b992"),
        "security": ("#254139", "#99dbc3"),
        "ai": ("#462c3a", "#e6a9c2"),
    },
}

CARD_GROUPS = {
    "conversion": ("pdf_images", "images_pdf", "text"),
    "page": ("merge", "split", "extract", "nup", "crop"),
    "content": ("watermark", "number", "redact"),
    "security": ("compress", "protect", "clean"),
    "ai": ("upscale", "ocr"),
}
CARD_GROUP = {key: group for group, keys in CARD_GROUPS.items() for key in keys}
CARD_RADIUS = 14
BUTTON_RADIUS = 10
CHIP_RADIUS = 10
CARD_GAP = 14
CARD_PADDING = 18
FONT_SIZES = {"title": 20, "card_title": 14, "body": 12, "caption": 11}
FALLBACK_FONTS = ("맑은 고딕", "Malgun Gothic", "Segoe UI")
_registered = []
FONT_FAMILY = "맑은 고딕"
BOLD_FAMILY = "맑은 고딕"


def resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return base.joinpath("assets", *parts)


def register_fonts():
    """Expose bundled font only in this process; never alter system font installation."""
    if sys.platform != "win32" or _registered:
        return
    for path in sorted(resource_path("fonts").glob("Pretendard-*.otf")):
        try:
            if ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0):
                _registered.append(str(path))
        except (OSError, AttributeError):
            continue


def font_family(root):
    """Pick the body family; bold text uses BOLD_FAMILY for a real bold face."""
    global FONT_FAMILY, BOLD_FAMILY
    installed = set(tkfont.families(root))
    for family in ("Pretendard", *FALLBACK_FONTS):
        if family in installed:
            FONT_FAMILY = BOLD_FAMILY = family
            # Pretendard Regular is thin on screen; Medium reads clearly. Bold
            # stays on the base family, whose own Bold face is used.
            if family == "Pretendard" and "Pretendard Medium" in installed:
                FONT_FAMILY = "Pretendard Medium"
            return FONT_FAMILY
    FONT_FAMILY = BOLD_FAMILY = "TkDefaultFont"
    return FONT_FAMILY


def set_mode(name):
    ctk.set_appearance_mode("Dark" if name == "dark" else "Light")


def colors(name):
    return PALETTES["dark" if name == "dark" else "default"]
