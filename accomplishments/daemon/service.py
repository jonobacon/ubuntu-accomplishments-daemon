from twisted.application.internet import TimerService
from twisted.application.service import MultiService
from twisted.application.service import Service
from twisted.python import log

import dbus.service

from accomplishments import util


class AccomplishmentsDaemonService(MultiService):
    """
    The top-level service that all other services should set as their parent.
    """
    def __init__(self, gpg_pub_key):
        MultiService.__init__(self)
        self.gpg_key = gpg_pub_key

    def startService(self):
        log.msg("Starting up accomplishments daemon ...")
        util.import_gpg_key(self.gpg_key)
        MultiService.startService(self)

    def stopService(self):
        log.msg("Shutting down accomplishments daemon ...")
        return MultiService.stopService(self)


class DBusService(MultiService):
    """
    A Twisted application service that tracks the DBus mainloop and the DBus
    session bus.
    """
    def __init__(self, main_loop, session_bus):
        MultiService.__init__(self)
        self.main_loop = main_loop
        self.session_bus = session_bus

    def startService(self):
        log.msg("Starting up DBus service ...")
        return MultiService.startService(self)

    def stopService(self):
        log.msg("Shutting down DBus service ...")
        return MultiService.stopService(self)


class DBusExportService(Service, dbus.service.Object):
    """
    A base class that is both a Twisted application service as well as a means
    for exporting custom objects across a given bus.
    """
    def __init__(self, bus_name, session_bus):
        self.bus_name = bus_name
        self.session_bus = session_bus

    def startService(self):
        log.msg("Starting up API exporter service ...")
        return Service.startService(self)

    def stopService(self):
        log.msg("Shutting down API exporter service ...")
        return Service.stopService(self)


class ScriptRunnerService(TimerService):
    """
    A simple wrapper for the TimerService that runs the scripts at the given
    intertal.
    """
    def __init__(self, interval, api):
        TimerService.__init__(self, interval, api.run_scripts, False)

    def startService(self):
        log.msg("Starting up script runner service ...")
        return TimerService.startService(self)

    def stopService(self):
        log.msg("Shutting down script runner service ...")
        return TimerService.stopService(self)
