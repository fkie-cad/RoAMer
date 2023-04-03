import os


def get_user_path():
    return os.path.join(*["C:" + os.sep, "Users", os.getenv("username")])
