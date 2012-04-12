# A stupid Python-specific wrapper for the libaccomplishments-daemon D-Bus API
# This should not be a Python library. It should be a
# GObject-introspection-capable C thing so anyone can use it. But someone else
# needs to write that because I'm crap at Vala.
import dbus

from twisted.python import log

from accomplishments.daemon import service


def daemon_is_registered():
    """
    """
    try:
        obj = dbus.SessionBus().get_object(
            "org.ubuntu.accomplishments", "/")
        return True
    except dbus.exceptions.DBusException:
        log.msg(
            "User does not have the accomplishments daemon "
            "available")
        return False


# XXX as a function, this needs to be renamed to a lower-case function name and
# not use the class naming convention of upper-case.
# 
# Hrm, on second thought... this is:
#  * a singleton object (SessionBus)
#  * obtaining an object indicated by string constants
#  * and then doing a lookup on these
# In other words, nothing changes ;-)
#
# As such, there's no need for this to be a function; instead, we can set our
# own module-level singleton, perhaps as part of the AccomplishmentsDBusService
# set up, since that object has access to all the configuration used here (bus
# name and bus path).
def Accomplishments():
    """
    """
    obj = dbus.SessionBus().get_object("org.ubuntu.accomplishments", "/")
    return dbus.Interface(obj, "org.ubuntu.accomplishments")


class AccomplishmentsDBusService(service.DBusExportService):
    """
    """
    def __init__(self, bus_name, session_bus, object_path="/", 
                 show_notifications=True):
        super(AccomplishmentsDBusService, self).__init__(bus_name, session_bus)
        bus_name = dbus.service.BusName(bus_name, bus=session_bus)
        dbus.service.Object.__init__(self, bus_name, object_path)
        self.show_notifications = show_notifications
        # XXX until all the imports are cleaned up and the code is organized
        # properly, we're doing the import here (to avoid circular imports).
        from accomplishments.daemon import api
        # this is not a subclass of dbus.service.Object *and* Accomplishments
        # because doing that confuses everything, so we create our own
        # private Accomplishments object and use it.
        self.api = api.Accomplishments(self, self.show_notifications)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def listAllAccomplishments(self):
        return self.api.listAllAccomplishments()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def listAllAccomplishmentsAndStatus(self):
        return self.api.listAllAccomplishmentsAndStatus()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def listAllAvailableAccomplishmentsWithScripts(self):
        return self.api.listAllAvailableAccomplishmentsWithScripts()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def getAllExtraInformationRequired(self):
        return self.api.getAllExtraInformationRequired()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def getAllExtraInformation(self):
        return self.api.getAllExtraInformation()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def listAccomplishmentInfo(self, accomplishment):
        return self.api.listAccomplishmentInfo(accomplishment)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def listTrophyInfo(self, trophy):
        return self.api.listTrophyInfo(trophy)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="b", out_signature="")
    def run_scripts(self, run_by_client):
        return self.api.run_scripts(run_by_client)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def getExtraInformation(self, app, info):
        return self.api.getExtraInformation(app, info)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="")
    def createExtraInformationFile(self, app, item, data):
        return self.api.createExtraInformationFile(app, item, data)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="")
    def saveExtraInformationFile(self, app, item, data):
        return self.api.saveExtraInformationFile(app, item, data)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="ss", out_signature="")
    def accomplish(self, app, accomplishment_name):
        trophy = self.api.accomplish(app, accomplishment_name)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="b")
    def register_trophy_dir(self, trophydir):
        return self.api.asyncapi.register_trophy_dir(trophydir)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="vv", out_signature="v")
    def getConfigValue(self, section, item):
        return self.api.getConfigValue(section, item)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="")
    def invalidateExtraInformation(self, extrainfo):
        return self.api.invalidateExtraInformation(extrainfo)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="vvv", out_signature="")
    def setConfigValue(self, section, item, value):
        return self.api.setConfigValue(section, item, value)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="b")
    def verifyU1Account(self):
        return self.api.verifyU1Account()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def getApplicationFullName(self,app):
        return self.api.getApplicationFullName(app)
        
    # XXX this looks like an unintentional duplicate of the "other"
    # trophy_received... I've moved them here together so that someone in the
    # know (Jono?) can clarify and remove the one that's not needed
    #@dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    #def trophy_received(self, trophy):
    #    pass
    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def trophy_received(self, trophy):
        t = "mytrophy"
        return t

    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def scriptrunner_start(self):
        pass

    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def scriptrunner_finish(self):
        pass
