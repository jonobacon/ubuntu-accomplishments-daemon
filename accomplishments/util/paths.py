import os
from accomplishments.util import get_data_path

def uses_system_lib():
    return os.path.dirname(__file__).startswith("/usr")

runs_in_branch = not uses_system_lib()
#systemdata_dir = "data/daemon/"
#media_dir      = "data/media/"
if not runs_in_branch:
    systemdata_dir = "/usr/share/accomplishments-daemon/"
    media_dir      = "/usr/share/accomplishments-daemon/media/"
else:
    localdatapath = get_data_path()
    systemdata_dir = os.path.join(localdatapath, "daemon")
    media_dir      = os.path.join(localdatapath, "media")
