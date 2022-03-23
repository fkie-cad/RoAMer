import os
import subprocess

user_path = "C:\\Users\\%s\\" % os.getenv("username")
subprocess.Popen(f"python {user_path}\\updater.py")