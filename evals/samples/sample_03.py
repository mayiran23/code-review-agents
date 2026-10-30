import os


def read_upload(filename):
    path = os.path.join("/data/uploads", filename)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()
