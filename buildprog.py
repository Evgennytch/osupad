import os
import subprocess
import sys

os.chdir(os.path.dirname(os.path.abspath(__file__)))
project_dir = os.path.dirname(os.path.abspath(__file__))

try:
    import customtkinter

    ctk_path = os.path.dirname(customtkinter.__file__)

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconsole",
        "--onefile",
        "--clean",
        "--name=osupad",
        "--distpath=release",
        "--workpath=build/release",
        "--specpath=build/release",
        f"--icon={os.path.join(project_dir, 'osu_keypad.ico')}",
        f"--add-data={ctk_path};customtkinter/",
        "--collect-all",
        "customtkinter",
        "--hidden-import=serial",
        "--hidden-import=serial.tools.list_ports",
        "app.py",
    ]

    print("Собираем EXE с полной упакованой serial-библиотекой...")
    subprocess.run(cmd, check=True)
    print("\nГотово: release/osupad.exe")

except Exception as e:
    print(f"\nПРОИЗОШЛА ОШИБКА: {e}")
    raise
