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
    def get_all_extra_information_required(self):
        return self.api.get_all_extra_information_required()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def get_all_extra_information(self):
        return self.api.get_all_extra_information()

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
        in_signature="b", out_signature="")
    def set_daemon_session_start(self,value):
        return self.api.set_daemon_session_start(value)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="b", out_signature="")
    def set_block_ubuntuone_notification_bubbles(self,value):
        return self.api.set_block_ubuntuone_notification_bubbles(value)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="b")
    def get_daemon_session_start(self):
        return self.api.get_daemon_session_start()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="b")
    def get_block_ubuntuone_notification_bubbles(self):
        return self.api.get_block_ubuntuone_notification_bubbles()

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
        in_signature="", out_signature="")
    def reload_accom_database(self):
        return self.api.reload_accom_database()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="a{sv}")
    def get_acc_data(self,accomID):
        return self.api.get_acc_data(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="b")   
    def get_acc_exists(self,accomID):
        return self.api.get_acc_exists(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_acc_title(self,accomID):
        return self.api.get_acc_title(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_acc_description(self,accomID):
        return self.api.get_acc_description(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_acc_collection(self,accomID):
        return self.api.get_acc_collection(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="as")
    def get_acc_categories(self,accomID):
        return self.api.get_acc_categories(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="b")
    def get_acc_needs_signing(self,accomID):
        return self.api.get_acc_needs_signing(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="as")
    def get_acc_depends(self,accomID):
        return self.api.get_acc_depends(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="b")
    def get_acc_is_unlocked(self,accomID):
        return self.api.get_acc_is_unlocked(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_trophy_path(self,accomID):
        return self.api.get_trophy_path(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="b")
    def get_acc_is_completed(self,accomID):
        return self.api.get_acc_is_completed(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="b")
    def get_published_status(self):
        return self.api.get_published_status()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_acc_script_path(self,accomID):
        return self.api.get_acc_script_path(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_acc_icon(self,accomID):
        return self.api.get_acc_icon(accomID)        
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_acc_icon_path(self,accomID):
        return self.api.get_acc_icon_path(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="v")
    def get_acc_needs_info(self,accomID):
        return self.api.get_acc_needs_info(self,accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="a{sv}")
    def get_trophy_data(self,accomID):
        return self.api.get_trophy_data(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="s")
    def get_collection_name(self,collection):
        return self.api.get_collection_name(collection)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="b")
    def get_collection_exists(self,collection):
        return self.api.get_collection_exists(collection)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="as")
    def get_collection_authors(self,collection):
        return self.api.get_collection_authors(collection)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="a{sas}")
    def get_collection_categories(self,collection):
        return self.api.get_collection_categories(collection)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="v")
    def get_collection_data(self,collection):
        return self.api.get_collection_data(collection)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="as")
    def list_accomplishments(self):
        return self.api.list_accomplishments()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="as")
    def list_trophies(self):
        return self.api.list_trophies()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="as")
    def list_opportunitues(self):
        return self.api.list_opportunitues()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="s", out_signature="as")
    def list_depending_on(self,accomID):
        return self.api.list_depending_on(accomID)
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="as")
    def list_unlocked(self):
        return self.api.list_unlocked()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="as")
    def list_unlocked_not_completed(self):
        return self.api.list_unlocked_not_completed()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="as")
    def list_collections(self):
        return self.api.list_collections()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="aa{sv}")
    def build_viewer_database(self):
        return self.api.build_viewer_database()
        
    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="s")
    def get_API_version(self):
        return self.api.get_API_version()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="")
    def publish_trophies_online(self):
        return self.api.publish_trophies_online()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
        in_signature="", out_signature="")
    def unpublish_trophies_online(self):
        return self.api.unpublish_trophies_online()
        
    # XXX this looks like an unintentional duplicate of the "other"
    # trophy_received... I've moved them here together so that someone in the
    # know (Jono?) can clarify and remove the one that's not needed
    #@dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    #def trophy_received(self, trophy):
    #    pass
    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def trophy_received(self, trophy):
        return trophy

    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def publish_trophies_online_completed(self, url):
        return url

    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def scriptrunner_start(self):
        pass

    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def scriptrunner_finish(self):
        pass

    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def ubuntu_one_account_ready(self):
        pass
