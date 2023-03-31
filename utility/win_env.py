import os

def get_user_path():
    return os.path.join(["C:", "Users", os.getenv("username")])