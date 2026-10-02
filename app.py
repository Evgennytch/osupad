"""Desktop configurator for the osu! RP2040 keypad.

Install dependencies once:
    py -m pip install customtkinter pyserial pystray pillow
Run on Windows:
    py app.py
"""

import re
import threading
import time
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
import serial
from serial.tools import list_ports
import pystray
from PIL import Image, ImageDraw


POLL_RATES = ("125", "250", "500", "750", "1000")
CONFIG_PATTERN = re.compile(
    r"^CFG:K1=(\d+),K2=(\d+),K3=(\d+),HZ=(\d+),DEB=(\d+),RGB=(\d+),(\d+),(\d+)$"
)


class KeypadApplication(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("osu! keypad")
        self.geometry("500x520")
        self.minsize(500, 520)
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self.serial_port = None
        self.connected_name = None
        self.last_search = 0.0
        self.tray_icon = None
        self.is_exiting = False

        ctk.set_appearance_mode("system")
        self.key_values = ["z", "x", "c"]
        self.key_labels = []
        self.poll_rate = ctk.StringVar(value="1000")
        self.debounce = ctk.IntVar(value=0)
        self.rgb = [ctk.IntVar(value=0), ctk.IntVar(value=80), ctk.IntVar(value=255)]
        self.port_value = ctk.StringVar(value="Автопоиск")
        self.status = ctk.StringVar(value="Поиск RP2040-Zero…")

        self._build_ui()
        self._start_tray()
        self.after(200, self.connection_tick)

    def _build_ui(self):
        frame = ctk.CTkFrame(self)
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        ctk.CTkLabel(frame, text="osu! keypad", font=ctk.CTkFont(size=24, weight="bold")).pack(pady=(14, 10))

        port_row = ctk.CTkFrame(frame, fg_color="transparent")
        port_row.pack(fill="x", padx=18, pady=5)
        ctk.CTkLabel(port_row, text="COM-порт", width=100, anchor="w").pack(side="left")
        self.port_menu = ctk.CTkOptionMenu(port_row, variable=self.port_value, values=["Автопоиск"], command=lambda _: self.connect_selected())
        self.port_menu.pack(side="left", fill="x", expand=True, padx=(5, 8))
        ctk.CTkButton(port_row, text="Обновить", width=82, command=self.refresh_ports).pack(side="right")

        keys_frame = ctk.CTkFrame(frame)
        keys_frame.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(keys_frame, text="Назначение кнопок (нажмите и выберите символ)").pack(pady=(8, 4))
        buttons_row = ctk.CTkFrame(keys_frame, fg_color="transparent")
        buttons_row.pack(pady=(0, 9))
        for index in range(3):
            button = ctk.CTkButton(buttons_row, text=f"K{index + 1}: {self.key_values[index]}", width=130,
                                   command=lambda i=index: self.capture_key(i))
            button.grid(row=0, column=index, padx=4)
            self.key_labels.append(button)

        rate_row = ctk.CTkFrame(frame, fg_color="transparent")
        rate_row.pack(fill="x", padx=18, pady=8)
        ctk.CTkLabel(rate_row, text="Частота опроса", width=120, anchor="w").pack(side="left")
        ctk.CTkOptionMenu(rate_row, variable=self.poll_rate, values=list(POLL_RATES), width=140).pack(side="left", padx=6)
        ctk.CTkLabel(rate_row, text="Гц").pack(side="left")

        debounce_row = ctk.CTkFrame(frame, fg_color="transparent")
        debounce_row.pack(fill="x", padx=18, pady=8)
        self.debounce_label = ctk.CTkLabel(debounce_row, text="Антидребезг: 0 мс (выключен)", width=220, anchor="w")
        self.debounce_label.pack(side="left")
        ctk.CTkSlider(debounce_row, from_=0, to=10, number_of_steps=10, variable=self.debounce,
                      command=lambda _: self.update_labels()).pack(side="left", fill="x", expand=True)

        colors = ctk.CTkFrame(frame)
        colors.pack(fill="x", padx=18, pady=8)
        self.color_preview = ctk.CTkLabel(colors, text="   ", width=42, height=42, corner_radius=8)
        self.color_preview.grid(row=0, column=0, rowspan=3, padx=10, pady=10)
        for index, name in enumerate(("R", "G", "B")):
            ctk.CTkLabel(colors, text=name, width=20).grid(row=index, column=1, padx=(0, 4))
            ctk.CTkSlider(colors, from_=0, to=255, number_of_steps=255, variable=self.rgb[index],
                          command=lambda _: self.update_labels()).grid(row=index, column=2, sticky="ew", padx=4, pady=3)
            ctk.CTkLabel(colors, textvariable=self.rgb[index], width=30).grid(row=index, column=3, padx=(4, 10))
        colors.grid_columnconfigure(2, weight=1)

        ctk.CTkButton(frame, text="Применить и сохранить", height=40, command=self.apply_config).pack(fill="x", padx=18, pady=(8, 6))
        ctk.CTkLabel(frame, textvariable=self.status, text_color=("#555555", "#bbbbbb")).pack(pady=(2, 10))
        self.update_labels()

    def update_labels(self):
        value = self.debounce.get()
        self.debounce_label.configure(text=f"Антидребезг: {value} мс" + (" (выключен)" if value == 0 else ""))
        red, green, blue = (item.get() for item in self.rgb)
        self.color_preview.configure(fg_color=f"#{red:02x}{green:02x}{blue:02x}")

    def capture_key(self, index):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Назначить клавишу")
        dialog.geometry("350x130")
        dialog.transient(self)
        dialog.grab_set()
        ctk.CTkLabel(dialog, text="Нажмите любую печатную ASCII-клавишу\n(букву, цифру или символ)", font=ctk.CTkFont(size=15)).pack(expand=True)

        def on_key(event):
            # event.char is intentionally used: the firmware maps printable US ASCII.
            if len(event.char) == 1 and 32 <= ord(event.char) <= 126:
                self.key_values[index] = event.char
                self.key_labels[index].configure(text=f"K{index + 1}: {event.char}")
                dialog.destroy()
            else:
                self.status.set("Поддерживаются печатные ASCII-символы.")

        dialog.bind("<KeyPress>", on_key)
        dialog.after(100, dialog.focus_force)

    @staticmethod
    def is_likely_keypad(port):
        text = " ".join(filter(None, [port.manufacturer, port.description, port.product])).lower()
        # 2E8A is Raspberry Pi's USB vendor ID.  Text fallback supports custom builds.
        return port.vid == 0x2E8A or "rp2040" in text or "tinyusb" in text or "waveshare" in text

    def refresh_ports(self):
        ports = list(list_ports.comports())
        names = ["Автопоиск"] + [f"{p.device} — {p.description}" for p in ports]
        self.port_menu.configure(values=names)
        if self.port_value.get() not in names:
            self.port_value.set("Автопоиск")
        self.connect_selected()

    def desired_device(self):
        selected = self.port_value.get()
        if selected != "Автопоиск":
            return selected.split(" — ", 1)[0]
        candidates = [p.device for p in list_ports.comports() if self.is_likely_keypad(p)]
        return candidates[0] if candidates else None

    def close_port(self):
        if self.serial_port:
            try:
                self.serial_port.close()
            except serial.SerialException:
                pass
        self.serial_port = None
        self.connected_name = None

    def connect_selected(self):
        device = self.desired_device()
        if not device:
            self.close_port()
            self.status.set("RP2040-Zero не найден.")
            return
        if self.serial_port and self.connected_name == device and self.serial_port.is_open:
            return
        self.close_port()
        try:
            # timeout=0 makes all subsequent reads non-blocking for the GUI.
            self.serial_port = serial.Serial(device, 115200, timeout=0, write_timeout=0.5)
            self.connected_name = device
            time.sleep(0.05)  # brief USB CDC settle, not a UI loop operation
            self.send_line("GET_CONFIG")
            self.status.set(f"Подключено: {device}")
        except (serial.SerialException, OSError) as error:
            self.close_port()
            self.status.set(f"Не удалось открыть {device}: {error}")

    def send_line(self, line):
        if not self.serial_port or not self.serial_port.is_open:
            raise serial.SerialException("Устройство не подключено")
        self.serial_port.write((line + "\n").encode("ascii"))

    def apply_config(self):
        self.connect_selected()
        try:
            values = [ord(key) for key in self.key_values]
            red, green, blue = (item.get() for item in self.rgb)
            command = (f"SET:K1={values[0]},K2={values[1]},K3={values[2]},HZ={self.poll_rate.get()},"
                       f"DEB={self.debounce.get()},RGB={red},{green},{blue}")
            self.send_line(command)
            self.status.set("Настройки отправлены и сохранены во Flash.")
        except (serial.SerialException, OSError) as error:
            self.close_port()
            self.status.set(f"Ошибка связи: {error}")

    def read_serial(self):
        if not self.serial_port or not self.serial_port.is_open:
            return
        try:
            while self.serial_port.in_waiting:
                line = self.serial_port.readline().decode("ascii", errors="replace").strip()
                match = CONFIG_PATTERN.match(line)
                if match:
                    data = [int(value) for value in match.groups()]
                    self.key_values = [chr(value) for value in data[:3]]
                    for index, key in enumerate(self.key_values):
                        self.key_labels[index].configure(text=f"K{index + 1}: {key}")
                    self.poll_rate.set(str(data[3]))
                    self.debounce.set(data[4])
                    for index in range(3): self.rgb[index].set(data[5 + index])
                    self.update_labels()
                    self.status.set(f"Конфигурация прочитана: {self.connected_name}")
                elif line.startswith("ERR:"):
                    self.status.set("Контроллер: " + line)
        except (serial.SerialException, OSError) as error:
            self.close_port()
            self.status.set(f"Соединение потеряно: {error}")

    def connection_tick(self):
        self.read_serial()
        if time.monotonic() - self.last_search > 2:
            self.last_search = time.monotonic()
            if not self.serial_port or not self.serial_port.is_open:
                self.refresh_ports()
        if not self.is_exiting:
            self.after(50, self.connection_tick)

    def _make_tray_image(self):
        image = Image.new("RGB", (64, 64), (30, 30, 35))
        draw = ImageDraw.Draw(image)
        for x, color in ((10, (255, 80, 90)), (26, (80, 210, 255)), (42, (120, 255, 130))):
            draw.rounded_rectangle((x, 18, x + 12, 46), radius=3, fill=color)
        return image

    def _start_tray(self):
        menu = pystray.Menu(
            pystray.MenuItem("Открыть", lambda: self.after(0, self.show_window), default=True),
            pystray.MenuItem("Выход", lambda: self.after(0, self.exit_application)),
        )
        self.tray_icon = pystray.Icon("osu_keypad", self._make_tray_image(), "osu! keypad", menu)
        threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def hide_to_tray(self):
        self.withdraw()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(150, lambda: self.attributes("-topmost", False))
        self.focus_force()

    def exit_application(self):
        self.is_exiting = True
        self.close_port()
        if self.tray_icon:
            self.tray_icon.stop()
        self.destroy()


if __name__ == "__main__":
    KeypadApplication().mainloop()
