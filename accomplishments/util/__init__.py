import logging
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


gettext.textdomain('accomplishments-daemon')


def get_version():
    return config.__version__


class NullHandler(logging.Handler):
    """
    """
    def emit(self, record):
        pass


def set_up_logging(opts):
    # add a handler to prevent basicConfig
    root = logging.getLogger()
    null_handler = NullHandler()
    root.addHandler(null_handler)

    formatter = logging.Formatter(
        "%(levelname)s:%(name)s: %(funcName)s() '%(message)s'")

    logger = logging.getLogger('accomplishments-daemon')
    logger_sh = logging.StreamHandler()
    logger_sh.setFormatter(formatter)
    logger.addHandler(logger_sh)

    # Set the logging level to show debug messages.
    if opts.verbose:
        logger.setLevel(logging.DEBUG)
        logger.debug('logging enabled')
    if opts.verbose > 1:
        logger.setLevel(logging.DEBUG)


def get_data_path():
    """Retrieve accomplishments-daemon data path

    This path is by default <accomplishments_daemon_lib_path>/../data/ in trunk
    and /usr/share/ubuntu-accomplishments-daemon in an installed version but this path
    is specified at installation time.
    """

    # Get pathname absolute or relative.
    path = os.path.join(
        os.path.dirname(accomplishments.__path__[0]),
        config.__ubuntu_accomplishments_daemon_data_directory__)
    abs_data_path = os.path.abspath(path)
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
