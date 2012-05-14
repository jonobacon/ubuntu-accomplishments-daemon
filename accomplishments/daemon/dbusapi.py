"""
(c) 2012, Jono Bacon, and the Ubuntu Accomplishments community.

This is the core Ubuntu Accomplishments daemon API as exposed via DBUS.

This file is licensed under the GNU Public License version 3.

If you are interested in contributing improvements or changes to this
program, please see http://wiki.ubuntu.com/Accomplishments for how to
get involved.
"""

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
    def get_all_accomplishments(self):
        return self.api.get_all_accomplishments()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def get_all_accomplishments_and_status(self):
        return self.api.get_all_accomplishments_and_status()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def get_all_available_accomplishments_with_scripts(self):
        return self.api.list_all_available_accomplishments_with_scripts()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def get_all_extra_information_required(self):
        return self.api.get_all_extra_information_required()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def get_all_extra_information(self):
        return self.api.get_all_extra_information()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def get_accomplishment_information(self, accomplishment):
        return self.api.get_accomplishment_information(accomplishment)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def get_trophy_information(self, trophy):
        return self.api.get_trophy_information(trophy)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="b", out_signature="")
    def run_scripts(self, run_by_client):
        return self.api.run_scripts(run_by_client)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="ss", out_signature="aa{sv}")
    def get_extra_information(self, app, info):
        return self.api.get_extra_information(app, info)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="")
    def create_extra_information_file(self, item, data):
        return self.api.create_extra_information_file(item, data)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="")
    def write_extra_information_file(self, item, data):
        return self.api.write_extra_information_file(item, data)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="")
    def accomplish(self, accomID):
        trophy = self.api.accomplish(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="b")
    def register_trophy_dir(self, trophydir):
        return self.api.asyncapi.register_trophy_dir(trophydir)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="vv", out_signature="v")
    def get_config_value(self, section, item):
        return self.api.get_config_value(section, item)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="")
    def invalidate_extra_information(self, extrainfo):
        return self.api.invalidate_extra_information(extrainfo)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="vvv", out_signature="")
    def write_config_file_item(self, section, item, value):
        return self.api.write_config_file_item(section, item, value)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="b")
    def verify_ubuntu_one_account(self):
        return self.api.verify_ubuntu_one_account()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_application_full_name(self,app):
        return self.api.get_application_full_name(app)
        
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
