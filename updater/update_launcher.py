import os
import subprocess

from utility.win_env import get_user_path

subprocess.Popen(["python", os.path.join(*[get_user_path(), "updater.py"])])
