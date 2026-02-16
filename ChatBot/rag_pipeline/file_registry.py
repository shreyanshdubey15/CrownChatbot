import json
import os

REGISTRY_PATH = "data/uploaded_files.json"


def get_uploaded_files():

    if not os.path.exists(REGISTRY_PATH):
        return []

    with open(REGISTRY_PATH, "r") as f:
        return json.load(f)


def add_uploaded_file(filename):

    files = get_uploaded_files()

    if filename not in files:
        files.append(filename)

        with open(REGISTRY_PATH, "w") as f:
            json.dump(files, f, indent=2)


def file_exists(filename):

    return filename in get_uploaded_files()


def clear_registry():

    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, "w") as f:
            json.dump([], f, indent=2)
