import os

def uses_system_lib():
    return os.path.dirname(__file__).startswith("/usr")

runs_in_branch = not uses_system_lib()
systemdata_dir = "data/daemon/"
media_dir      = "data/media/"
if not runs_in_branch:
    systemdata_dir = "/usr/share/accomplishments-daemon/"
    media_dir      = "/usr/share/accomplishments-daemon/media/"
