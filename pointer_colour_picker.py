# Seat Open Blue = RGB (138, 170, 249), #8AAAF9
# Seat Closed Gray = RGB (175, 175, 175), #AFAFAF
# Background Light Gray = RGB (204, 204, 204), #CCCCCC


import time
import tkinter as tk
from tkinter import messagebox
import pyautogui
import threading
import csv
import os
from datetime import datetime

REFRESH_HZ = 20  # update rate (times per second)

def rgb_to_hex(r, g, b):
    return f"#{r:02X}{g:02X}{b:02X}"

class PointerColorPicker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Pointer Color Picker")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        # Small, dark-ish UI
        bg = "#18181b"
        fg = "#e5e7eb"
        mono = ("Consolas", 12) if os.name == "nt" else ("Menlo", 12)

        frame = tk.Frame(self.root, bg=bg, padx=10, pady=10)
        frame.pack()

        self.xy_var = tk.StringVar(value="x=0  y=0")
        self.rgb_var = tk.StringVar(value="RGB(0, 0, 0)")
        self.hex_var = tk.StringVar(value="#000000")

        tk.Label(frame, textvariable=self.xy_var, font=mono, fg=fg, bg=bg).pack(anchor="w")
        tk.Label(frame, textvariable=self.rgb_var, font=mono, fg=fg, bg=bg).pack(anchor="w")
        self.hex_label = tk.Label(frame, textvariable=self.hex_var, font=mono, fg=fg, bg=bg)
        self.hex_label.pack(anchor="w", pady=(0,8))

        # Color swatch
        self.swatch = tk.Canvas(frame, width=120, height=24, highlightthickness=1, highlightbackground="#3f3f46", bg="#000000")
        self.swatch.pack()

        # Help line
        help_text = "Space: Copy   S: Log CSV   Q/Esc: Quit"
        tk.Label(frame, text=help_text, font=("Segoe UI", 9), fg="#a1a1aa", bg=bg).pack(anchor="w", pady=(8,0))

        # Bind keys
        self.root.bind("<space>", self.copy_to_clipboard)
        self.root.bind("<s>", self.toggle_logging)
        self.root.bind("<S>", self.toggle_logging)
        self.root.bind("<Escape>", self.quit)
        self.root.bind("<q>", self.quit)
        self.root.bind("<Q>", self.quit)

        # Logging
        self.logging = False
        self.csv_path = "samples.csv"
        self.csv_file = None
        self.csv_writer = None

        # Update loop in a thread so UI stays responsive
        self._stop = threading.Event()
        self.thread = threading.Thread(target=self.update_loop, daemon=True)
        self.thread.start()

        # Position window a bit off the top-left so it doesn't block where you’re hovering
        self.root.geometry("+60+60")

        # Handle clean exit
        self.root.protocol("WM_DELETE_WINDOW", self.quit)

    def get_pointer_info(self):
        x, y = pyautogui.position()
        # pyautogui.pixel is usually faster than screenshot().getpixel
        try:
            r, g, b = pyautogui.pixel(x, y)
        except Exception:
            # Fallback if backend has issues
            pix = pyautogui.screenshot(region=(x, y, 1, 1)).getpixel((0, 0))
            r, g, b = pix[0], pix[1], pix[2]
        return x, y, r, g, b

    def update_loop(self):
        interval = 1.0 / REFRESH_HZ
        while not self._stop.is_set():
            x, y, r, g, b = self.get_pointer_info()
            hex_color = rgb_to_hex(r, g, b)

            # Update UI
            self.xy_var.set(f"x={x}  y={y}")
            self.rgb_var.set(f"RGB({r}, {g}, {b})")
            self.hex_var.set(hex_color)
            self.swatch.configure(bg=hex_color)

            # Logging if enabled
            if self.logging:
                self.ensure_csv()
                self.csv_writer.writerow({
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "x": x, "y": y,
                    "r": r, "g": g, "b": b,
                    "hex": hex_color
                })

            time.sleep(interval)

    def ensure_csv(self):
        if self.csv_file is None:
            new_file = not os.path.exists(self.csv_path)
            self.csv_file = open(self.csv_path, "a", newline="", encoding="utf-8")
            self.csv_writer = csv.DictWriter(self.csv_file, fieldnames=["timestamp", "x", "y", "r", "g", "b", "hex"])
            if new_file:
                self.csv_writer.writeheader()

    def copy_to_clipboard(self, event=None):
        xtext = self.xy_var.get()
        rgbtext = self.rgb_var.get()
        hextext = self.hex_var.get()
        payload = f"{xtext}  {rgbtext}  {hextext}"
        self.root.clipboard_clear()
        self.root.clipboard_append(payload)
        self.toast("Copied", f"{payload}")

    def toggle_logging(self, event=None):
        self.logging = not self.logging
        if self.logging:
            self.toast("Logging ON", f"Writing samples to {self.csv_path}")
        else:
            self.toast("Logging OFF", "CSV logging stopped")
            if self.csv_file:
                self.csv_file.flush()
                self.csv_file.close()
                self.csv_file = None
                self.csv_writer = None

    def toast(self, title, msg):
        # quick non-blocking toast in title bar
        self.root.title(f"{title} • Pointer Color Picker")
        # reset after a short delay
        self.root.after(1200, lambda: self.root.title("Pointer Color Picker"))

    def quit(self, event=None):
        self._stop.set()
        try:
            if self.csv_file:
                self.csv_file.flush()
                self.csv_file.close()
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    Picker = PointerColorPicker()
    Picker.run()

