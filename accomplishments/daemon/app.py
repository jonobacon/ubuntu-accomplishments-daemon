from optparse import OptionParser

from twisted.application.internet import TimerService
from twisted.application.service import Application

from accomplishments.daemon import dbusapi
from accomplishments.daemon import service
from accomplishments.daemon import api


# XXX these won't work with twistd; we need to write a twistd plugin to support
# additional command line options.
def parse_options():
    parser = OptionParser()
    parser.set_defaults(suppress_notifications=False)
    parser.add_option("--trophies-path", dest="trophies_path", default=None)
    parser.add_option("--accomplishments-path", dest="accomplishments_installpaths",
                      default=None)
    parser.add_option("--suppress-notifications", action="store_true",
                      dest="suppress_notifications")
    return parser.parse_args()


def applicationFactory(app_name="", bus_name="", main_loop=None,
                       session_bus=None, object_path="/", update_interval=3600,
                       gpg_key=""):
    # create the application object
    application = Application(app_name)
    # create the top-level service object that will contain all others; it will
    # not shutdown until all child services have been terminated
    top_level_service = service.AccomplishmentsDaemonService(gpg_key)
    top_level_service.setServiceParent(application)
    # create the service that all DBus services will rely upon (this parent
    # service will wait until child DBus services are shutdown before it shuts
    # down
    dbus_service = service.DBusService(main_loop, session_bus)
    dbus_service.setServiceParent(top_level_service)
    # create a child dbus serivce
    dbus_export_service = dbusapi.AccomplishmentsDBusService(
        bus_name, session_bus, object_path=object_path,
        show_notifications=True)
    dbus_export_service.setServiceParent(dbus_service)
    # create a service that will run the scripts at a regular interval
    timer_service = service.ScriptRunnerService(
        update_interval, dbus_export_service.api)
    timer_service.setServiceParent(top_level_service)
    
    return application
