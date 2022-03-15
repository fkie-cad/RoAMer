import zipfile
import os
import shutil
import subprocess

from ctypes import windll

user_path = "C:\\Users\\%s\\" % os.getenv("username")
roamer_repo_path = user_path + "roamer_repo"
roamer_zip_path = user_path + "roamer.zip"

def extract(zip_path, target_path):
    if os.path.exists(target_path):
        shutil.rmtree(target_path)
    with zipfile.ZipFile(zip_path,"r") as zf:
        zf.extractall(target_path)
    os.remove(zip_path)

def send_keycode(key_code):
    windll.user32.keybd_event(key_code, 0x45, 1 | 0, 0)
    windll.user32.keybd_event(key_code, 0x45, 1 | 2, 0)


extract(roamer_zip_path, roamer_repo_path)

compile_process = subprocess.Popen(roamer_repo_path+"\\compile.bat", cwd=roamer_repo_path)
compile_process.wait()

shutil.copy(roamer_repo_path+"\\unpacker\\dist\\main.exe", user_path+"main.exe")
shutil.copy(roamer_repo_path+"\\receiver\\dist\\main.exe", user_path+"Desktop\\roamer.exe")


send_keycode(0x0D) # Enter
send_keycode(ord("C"))
send_keycode(ord("L"))
send_keycode(ord("S"))
send_keycode(0x0D) # Enter
send_keycode(0x26) # Up
send_keycode(0x26) # Up
send_keycode(0x0D) # Enter