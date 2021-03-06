import optparse
import os

import gettext
from gettext import gettext as _

from twisted.internet import defer
from twisted.internet import protocol
from twisted.internet import reactor
from twisted.python import log

import accomplishments
from accomplishments import config
from accomplishments import exceptions

from accomplishments.util.paths import locale_dir
gettext.bindtextdomain('accomplishments-daemon', locale_dir)
gettext.textdomain('accomplishments-daemon')


def get_version():
    return config.__version__

def get_data_path():
    # XXX: NOTE: This function will most likely work incorrectly when daemon is installed in non-default path.
    # Luckily, this function is no longer used anywhere.
    # If you feel you need to get this path, please refer to utils/paths.py
    # instead.
    """Retrieve accomplishments-daemon data path

    This path is by default <accomplishments_daemon_lib_path>/../data/ in trunk
    and /usr/share/ubuntu-accomplishments-daemon in an installed version but this path
    is specified at installation time.
    """

    # Get pathname absolute or relative.
    path = os.path.join(accomplishments.__path__[0],
                        config.__accomplishments_daemon_data_directory__)
    abs_data_path = os.path.abspath(path)
    log.msg("MODULE DIR")
    log.msg(accomplishments.__path__[0])
    log.msg("ABS_DATA_PATH:")
    log.msg(abs_data_path)
    if not os.path.exists(abs_data_path):
        msg = "Could not find the project data directory."
        raise exceptions.PathNotFound(msg)
    return abs_data_path


def get_data_file(*path_segments):
    """Get the full path to a data file.

    Returns the path to a file underneath the data directory (as defined by
    `get_data_path`). Equivalent to os.path.join(get_data_path(),
    *path_segments).
    """
    return os.path.join(get_data_path(), *path_segments)


def parse_options():
    """Support for command line options"""
    parser = optparse.OptionParser(version="%%prog %s" % get_version())
    parser.add_option(
        "-v", "--verbose", action="count", dest="verbose",
        help=_("Show debug messages (-vv debugs accomplishments_daemon_lib also)"))
    parser.add_option(
        "-c", "--clear-trophies", action="count", dest="clear",
        help=_("Clear your trophies collection"))
    (options, args) = parser.parse_args()
    return options


class SubprocessReturnCodeProtocol(protocol.ProcessProtocol):
    """
    """
    def __init__(self, command=""):
        self.command = command

    def connectionMade(self):
        self.returnCodeDeferred = defer.Deferred()

    def processEnded(self, reason):
        self.returnCodeDeferred.callback(reason.value.exitCode)

    def outReceived(self, data):
        log.msg("Got process results: %s" % data)

    def errReceived(self, data):
        log.err("Got non-zero exit code for process: %s" % (
            " ".join(self.command),))
        log.msg(data)


def import_gpg_key(pub_key):
    """
    """
    cmd = ["gpg", "--import", pub_key]
    gpg = SubprocessReturnCodeProtocol(cmd)
    gpg.deferred = defer.Deferred()
    process = reactor.spawnProcess(gpg, cmd[0], cmd, env=None)
    return gpg.deferred
