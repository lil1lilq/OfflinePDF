"""One document mark shared by the app header, window and Windows executable."""

import sys
from pathlib import Path

from PIL import Image, ImageTk


def set_brand(root, canvas):
    folder = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "assets"
    with Image.open(folder / "app.png") as source:
        window = ImageTk.PhotoImage(source, master=root)
        header = ImageTk.PhotoImage(source.resize((32, 32), Image.Resampling.LANCZOS), master=root)
    root.offline_pdf_brand = (window, header)
    root.iconphoto(True, window)
    canvas.configure(bg="#092956")
    canvas.create_image(0, 0, image=header, anchor="nw")
