import os
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))

try:
    import customtkinter

    ctk_path = os.path.dirname(customtkinter.__file__)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--onefile",
        f"--add-data={ctk_path};customtkinter/",
        "--collect-all",
        "customtkinter",
        "--collect-all",
        "serial",  # Забирает всё, что связано с serial
        "--collect-all",
        "pyserial",  # Забирает сам пакет pyserial
        "--hidden-import=serial",
        "--hidden-import=serial.tools.list_ports",  # Часто теряется именно список портов!
        "app.py",
    ]

    print("Собираем EXE с полной упакованой serial-библиотекой...")
    subprocess.run(cmd)
    print("\nГОТОВО! Пробуй запускать из dist/")

except Exception as e:
    print(f"\nПРОИЗОШЛА ОШИБКА: {e}")

input("\nНажми Enter, чтобы закрыть окно...")