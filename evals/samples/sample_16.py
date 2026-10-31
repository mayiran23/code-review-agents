import os

BASE_DIR = "/data/configs"


def read_config(name):
    path = os.path.join(BASE_DIR, os.path.basename(name))
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
