# -*- Mode: Python; coding: utf-8; indent-tabs-mode: nil; tab-width: 4 -*-
### BEGIN LICENSE
# This file is in the public domain
### END LICENSE
from gi.repository import Gtk # pylint: disable=E0611

from accomplishments import util
from accomplishments.gui import TrophyinfoWindow
import signal


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    options = util.parse_options()
    util.set_up_logging(options)
    # Run the application.
    window = TrophyinfoWindow.TrophyinfoWindow()
    window.show()
    Gtk.main()
