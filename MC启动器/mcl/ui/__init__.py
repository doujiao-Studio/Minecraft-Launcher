"""UI 包：基于 Tkinter/ttk 的桌面界面。"""
from .app import MainWindow


def run():
    import tkinter as tk
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
