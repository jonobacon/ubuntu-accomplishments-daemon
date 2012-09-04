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
    try:
        obj = dbus.SessionBus().get_object(
            "org.ubuntu.accomplishments", "/")
        return True
    except dbus.exceptions.DBusException:
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
        """DOCS NEEDED"""

        return self.api.get_all_extra_information_required()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="aa{sv}")
    def get_all_extra_information(self):
        """
        Returns all the extra-information data available for the user.

        For more information on how extra-information works, see https://wiki.ubuntu.com/Accomplishments/Creating/Guide/Theory

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        The dictionaries returned have a series of fields:

         * **needs-information** - the name of this information field (e.g. `launchpad-email`).
         * **value** - the user's data for this field (e.g. `bruce@ironmaiden.com` for `launchpad-email`).
         * **regex** - a regular expression that defines the structure of the information.
         * **description** - a summary of the information.
         * **label** - a human readable description of the information.
         * **collection** - the collection this information is used in.
         * **example** - an example of this field set.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(dict)** - a set of dictionaries with the data for extra-information.
        Example:
            >>> obj.get_all_extra_information()
            {dbus.String(u'regex'): dbus.String(u'^(https?://)?askubuntu.com/users/\\d+/.*', variant_level=1), dbus.String(u'description'): dbus.String(u'The URL of your profile page on Ask Ubuntu', variant_level=1), dbus.String(u'value'): dbus.String(u'http://askubuntu.com/users/42996/jonobacon', variant_level=1), dbus.String(u'label'): dbus.String(u'Ask Ubuntu Profile URL', variant_level=1), dbus.String(u'needs-information'): dbus.String(u'askubuntu-user-url', variant_level=1), dbus.String(u'collection'): dbus.String(u'ubuntu-community', variant_level=1), dbus.String(u'example'): dbus.String(u'http://askubuntu.com/users/NUMBER/USERNAME', variant_level=1)}, signature=dbus.Signature('sv')), dbus.Dictionary({dbus.String(u'regex'): dbus.String(u'', variant_level=1), dbus.String(u'description'): dbus.String(u'The email address used for launchpad.net', variant_level=1), dbus.String(u'value'): dbus.String(u'jono@ubuntu.com', variant_level=1), dbus.String(u'label'): dbus.String(u'Launchpad Email', variant_level=1), dbus.String(u'needs-information'): dbus.String(u'launchpad-email', variant_level=1), dbus.String(u'collection'): dbus.String(u'ubuntu-community', variant_level=1), dbus.String(u'example'): dbus.String(u'', variant_level=1)}
        """
        return self.api.get_all_extra_information()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="v", out_signature="")
    def run_scripts(self, accomIDlist=None):
        return self.api.run_scripts(accomIDlist)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="")
    def run_script(self, accomID):
        return self.api.run_script(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="ss", out_signature="aa{sv}")
    def get_extra_information(self, collection, info):
        """
        Retrieve the data for the current user for the specified extra-information.

        It is common for accomplishments to require additional information to verify their completion. Clients
        should ask for this information and then use this function to write the information to the correct part
        of the trophy share. You can read more about how Extra Information works at https://wiki.ubuntu.com/Accomplishments/Creating/Guide/Theory

        As an example, if an accomplishment requires `launchpad-email` and the data for that information is `dave@megadeth.com`, this
        will be written to `~/.local/share/accomplishments/trophies/.extrainformation/launchpad-email` and the file will contain
        `dave@megadeth.com`.

        This function gets this data for you. It returns a dictionary with the following fields:

         * **<extra-information-field>** - the extra-information field type has the data associated with it (e.g. { 'launchpad-email' : 'george@cc.com'})
         * **label** - the human-readable label for the extra-information field (e.g. 'Launchpad Email' for `launchpad-email`).

        Args:
            collection (str): the collection that the extra-information applies to.

            info (str): the name of the extra-information type.

        Returns:
            (dict) dictionary of data for the specified field.

        Example:
            >>> obj.get_extra_information("ubuntu-community", "launchpad-email")
            {dbus.String(u'launchpad-email'): dbus.String(u'george@cc.com', variant_level=1), dbus.String(u'label'): dbus.String(u'Launchpad Email', variant_level=1)}
        """

        return self.api.get_extra_information(collection, info)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="")
    def create_extra_information_file(self, item, data):
        """
        Create an extra-information file that resides in the user's trophy share.

        It is common for accomplishments to require additional information to verify their completion. Clients
        should ask for this information and then use this function to write the information to the correct part
        of the trophy share. You can read more about how Extra Information works at https://wiki.ubuntu.com/Accomplishments/Creating/Guide/Theory

        As an example, if an accomplishment requires `launchpad-email` and the data for that information is `dave@megadeth.com`, this
        will be written to `~/.local/share/accomplishments/trophies/.extrainformation/launchpad-email` and the file will contain
        `dave@megadeth.com`. Never write to this location directly, just use this function to do this.

        Args:
            * **item** - (str) the extra-information type in question.
            * **data** - (str) the data for the specified item.
        Returns:
            None
        Example:
            >>> obj.create_extra_information_file("launchpad-email", "dave@megadeth.com")
        """

        return self.api.create_extra_information_file(item, data)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="b", out_signature="")
    def set_daemon_session_start(self, value):
        return self.api.set_daemon_session_start(value)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="b", out_signature="")
    def set_block_ubuntuone_notification_bubbles(self, value):
        return self.api.set_block_ubuntuone_notification_bubbles(value)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="b")
    def get_daemon_session_start(self):
        """DOCS NEEDED"""

        return self.api.get_daemon_session_start()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="b")
    def get_block_ubuntuone_notification_bubbles(self):
        """
        Returns whether the user has chosen to block Ubuntu One sync-daemon bubbles.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.


        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(bool)** - returns `True` if the bubbles are blocked, and `False` if not.
        Example:
            >>> obj.get_block_ubuntuone_notification_bubbles()
            True
        """

        return self.api.get_block_ubuntuone_notification_bubbles()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="")
    def write_extra_information_file(self, item, data):
        return self.api.write_extra_information_file(item, data)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="")
    def accomplish(self, accomID):
        """
        This function will accomplish the specified accomplishment.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        For this function to work, the specified accomplishment needs to exist on the system. For more details of how to create
        accomplishments and add them to a collection, see https://wiki.ubuntu.com/Accomplishments/Creating

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            None
        Example:
            >>> obj.accomplish("ubuntu-community/registered-on-launchpad")
        """
        trophy = self.api.accomplish(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="b")
    def register_trophy_dir(self, trophydir):
        return self.api.asyncapi.register_trophy_dir(trophydir)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="vv", out_signature="v")
    def get_config_value(self, section, item):
        """
        Returns the required value from the configuration file. For a list of available values
        see https://wiki.ubuntu.com/Accomplishments/GetInvolved/Hacking#Configuration_Files

        Config files are stored in Python ConfigParser format in which you look up the value by
        section and value.

        Args:
            * **section** - (str) the section in the config file (usually `config`).
            * **value** - (str) the value you want the data for.
        Returns:
            * **(str)** - the name of the collection.
        Example:
            >>> obj.get_collection_authors("config", "has_u1")
            True
        """
        return self.api.get_config_value(section, item)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="")
    def invalidate_extra_information(self, extrainfo):
        """DOCS NEEDED"""

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
    def get_accom_data(self, accomID):
        """
        Returns a database of accomplishment information on the system.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        All accomplishments have information about the accomplishment itself, and this function returns all of this data for the
        specified accomplishment. This is often useful for displaying this information to the user.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(dict)** - the data for the accomplishment.
        Example:
            >>> obj.build_viewer_database()
            { dbus.String(u'lang'): dbus.String(u'en', variant_level=1), dbus.String(u'needs-signing'): dbus.String(u'true', variant_level=1), dbus.String(u'date-completed'): dbus.String(u'2012-06-12 22:12', variant_level=1), dbus.String(u'set'): dbus.String(u'infrastructure', variant_level=1), dbus.String(u'locked'): dbus.Boolean(False, variant_level=1), dbus.String(u'help'): dbus.String(u'#launchpad on Freenode', variant_level=1), dbus.String(u'links'): dbus.String(u'http://www.launchpad.net', variant_level=1), dbus.String(u'title'): dbus.String(u'Registered on Launchpad', variant_level=1), dbus.String(u'script-path'): dbus.String(u'/home/jono/source/ubuntu-community-accomplishments/scripts/ubuntu-community/infrastructure/registered-on-launchpad.py', variant_level=1), dbus.String(u'base-path'): dbus.String(u'/home/jono/source/ubuntu-community-accomplishments/accomplishments/ubuntu-community', variant_level=1), dbus.String(u'completed'): dbus.Boolean(True, variant_level=1), dbus.String(u'author'): dbus.String(u'Jono Bacon <jono@ubuntu.com>', variant_level=1), dbus.String(u'collection'): dbus.String(u'ubuntu-community', variant_level=1), dbus.String(u'summary'): dbus.String(u'Launchpad is a website in which we do much of our work in Ubuntu. There we build packages, file and fix bugs, perform translations, manage code, and other activities.\\nYou will need to register an account with Launchpad to participate in much of the Ubuntu community. Fortunately, registering is simple, safe, and free.', variant_level=1), dbus.String(u'needs-information'): dbus.String(u'launchpad-email', variant_level=1), dbus.String(u'steps'): dbus.String(u'Load a web browser on your computer.\\nIn your web browser go to <tt>http://www.launchpad.net</tt>.\\nClick the <i>Register</i> link in the corner of the screen to register.', variant_level=1), dbus.String(u'icon'): dbus.String(u'default.png', variant_level=1), dbus.String(u'type'): dbus.String(u'accomplishment', variant_level=1), dbus.String(u'categories'): dbus.Array([dbus.String(u'Launchpad')], signature=dbus.Signature('s'), variant_level=1), dbus.String(u'description'): dbus.String(u'Registered a Launchpad account', variant_level=1) }
        """
        return self.api.get_accom_data(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="b")
    def get_accom_exists(self, accomID):
        """
        Returns whether the specified accomplishment is recognized on the system.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(bool)** - returns `True` is the accomplishment exists, and `False` if not.
        Example:
            >>> obj.get_accom_exists("ubuntu-community/registered-on-launchpad")
            True
        """

        return self.api.get_accom_exists(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="s")
    def get_accom_title(self, accomID):
        """
        Returns the title name of the specified accomplishment.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(str)** - the title of the accomplishment.
        Example:
            >>> obj.get_accom_exists("ubuntu-community/registered-on-launchpad")
            'Registered on Launchpad'
        """

        return self.api.get_accom_title(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="s")
    def get_accom_description(self, accomID):
        return self.api.get_accom_description(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="s")
    def get_accom_collection(self, accomID):
        """
        Returns the collection that a given accomplishment is part of.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        This function returns the collection that the accomplishment specified by `accomID`) is part of.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(str)** - the collection name.
        Example:
            >>> obj.get_accom_collection("ubuntu-community/registered-on-launchpad")
            ubuntu-community
        """

        return self.api.get_accom_collection(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="as")
    def get_accom_categories(self, accomID):
        """
        Returns a list of categories that the specified accomplishment is part of.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Categories can be specified in accomplishments as singular (e.g. `Ask Ubuntu`) or also include sub-categories
        (e.g. `Ask Ubuntu:Asking`); this function returns the categories in these formats.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(list)** - the list of categories.
        Example:
            >>> obj.get_accom_categories("ubuntu-community/registered-on-launchpad")
            ["Launchpad"]
        """
        return self.api.get_accom_categories(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="b")
    def get_accom_needs_signing(self, accomID):
        """
        Returns whether the specified accomplishment needs to be signed (verified) or not.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Global accomplishments, that is...accomplishments that are within the context of community, typically need to be verified
        to ensure people don't fake them. I know, who would think that people would fake these kinds of things. ;-)

        Accomplishments that need verifying specify this requirement, and this function returns whether the specified accomplishments
        needs signing (verifying) or not.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(bool)** - `True` if the accomplishment needs signing, `False` if not.
        Example:
            >>> obj.get_accom_categories("ubuntu-community/registered-on-launchpad")
            True
        """

        return self.api.get_accom_needs_signing(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="as")
    def get_accom_depends(self, accomID):
        """
        Returns a list of accomplishments that the accomplishment you pass depends on.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Accomplishments can depend on other accomplishments before they are completed: if an accomplishment has not had it's
        dependency satisfied, it should be shown in clients as locked.

        Accomplishments can specify multiple dependencies and this function returns a list of dependencies that the accomplishment
        you pass to this function depends on. These dependencies are also returns as accomplishment IDs. If no dependencies exist for
        the specified accomplishment, an empty list is returned.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(list)** - the list of dependencies for the accomplishment.
        Example:
            >>> obj.get_accom_depends("ubuntu-community/ubuntu-member")
            ["ubuntu-community/registered-on-launchpad"]
        """

        return self.api.get_accom_depends(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="b")
    def get_accom_is_unlocked(self, accomID):
        """
        Returns whether the specified accomplishment is unlocked or not (whether it's dependencies have been satisfied or not).

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Accomplishments can depend on other accomplishments before they are completed: if an accomplishment has not had it's
        dependency satisfied, it should be shown in clients as locked. This function checks whether such dependencies have been
        completed or not.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(bool)** - `True` if the dependencies have been completed, `False` if not.
        Example:
            >>> obj.get_accom_is_unlocked("ubuntu-community/registered-on-launchpad")
            True
        """

        return self.api.get_accom_is_unlocked(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="s")
    def get_trophy_path(self, accomID):
        return self.api.get_trophy_path(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="b")
    def get_accom_is_accomplished(self, accomID):
        """
        Returns whether the specified accomplishment is accomplished or not.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(bool)** - `True` if the accomplishment has been completed, `False` if not.
        Example:
            >>> obj.get_accom_is_accomplished("ubuntu-community/registered-on-launchpad")
            True
        """

        return self.api.get_accom_is_accomplished(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="b")
    def get_published_status(self):
        """
        Returns whether the user has opted to publish their accomplishments online.

        Args:
            None
        Returns:
            (bool) returns `True` if the user has opted to publish online, or `False` if not.
        Example:
            >>> obj.get_published_status()
            True
        """

        return self.api.get_published_status()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="s")
    def get_accom_script_path(self, accomID):
        """
        Returns the corrosponsing script for the accomplishment.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Many accomplishments have corrosponding scripts (although not all do), and this function returns a full path to the
        script.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(str)** - the full path to the script.
        Example:
            >>> obj.get_accom_script_path("ubuntu-community/registered-on-launchpad")
            /usr/share/accomplishments/scripts/ubuntu-community/infrastructure/registered-on-launchpad.py
        """

        return self.api.get_accom_script_path(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="s")
    def get_accom_icon(self, accomID):
        """
        Returns the icon name for the specified accomplishment.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        Note: this function only passes the icon name and not the full path to the icon. If you need this you should use
        `get_accom_icon_path()`.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(str)** - the name of the icon.
        Example:
            >>> obj.get_accom_icon("ubuntu-community/registered-on-launchpad")
            default.png
        """
        return self.api.get_accom_icon(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="s")
    def get_accom_icon_path(self, accomID):
        """
        Returns the icon name for the specified accomplishment.

        Every accomplishment has a unique identifier called an `Accomplishment ID` that is comprised of the collection
        and the name of the accomplishment itself (e.g. `ubuntu-community` collection and `registered-in-launchpad`
        accomplishment has an accomplishment ID of `ubuntu-community/registered-on-launchpad`). You pass this function this
        `Accomplishment ID` as it's parameter.

        If you don't need the full path and just need the icon name, use `get_accom_icon()`.

        Args:
            * **accomID** - (str) the `Accomplishment ID` for a given accomplishment (e.g. `ubuntu-community/registered-on-launchpad`).
        Returns:
            * **(str)** - the full path to the icon.
        Example:
            >>> obj.get_accom_icon_path("ubuntu-community/registered-on-launchpad")
            /home/jono/.cache/accomplishments/trophyimages/ubuntu-community/default.png
        """
        return self.api.get_accom_icon_path(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="v")
    def get_accom_needs_info(self, accomID):
        """DOCS NEEDED"""
        return self.api.get_accom_needs_info(self, accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="a{sv}")
    def get_trophy_data(self, accomID):
        return self.api.get_trophy_data(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="s")
    def get_collection_name(self, collection):
        """
        Returns the name of the current collection.

        Every collection has an identifier (e.g. `ubuntu-community`) that
        we use to refer to the group of accomplishments that form that collection.

        This function returns the name of the current collection in a human-readable format.

        Args:
            * **collection** - (str) the accomplishments collection identifier (e.g. `ubuntu-community`)
        Returns:
            * **(str)** - the name of the collection.
        Example:
            >>> obj.get_collection_authors("ubuntu-community")
            'Ubuntu Community'
        """
        return self.api.get_collection_name(collection)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="b")
    def get_collection_exists(self, collection):
        """
        Returns whether the collection exists or not on the disk.

        Every collection has an identifier (e.g. `ubuntu-community`) that
        we use to refer to the group of accomplishments that form that collection.

        This function returns a boolean value of whether the collection exists
        on the current installation.

        Args:
            * **collection** - (str) the accomplishments collection identifier (e.g. `ubuntu-community`)
        Returns:
            * **(bool)** - True if the collection exists, False if it doesn't.
        Example:
            >>> obj.get_collection_exists("ubuntu-community")
            True
        """

        return self.api.get_collection_exists(collection)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="as")
    def get_collection_authors(self, collection):
        """
        Returns a list of authors for a given collection.

        Every collection has an identifier (e.g. `ubuntu-community`) that
        we use to refer to the group of accomplishments that form that collection.

        This function returns all authors (without duplicates) for the collection
        passed to it. Data is returned in the following format:

            `Forename Surname <email address>`

        Args:
            * **collection** - (str) the accomplishments collection identifier (e.g. `ubuntu-community`)
        Returns:
            * **(list)** - the list of categories from that collection.
        Example:
            >>> obj.get_collection_authors("ubuntu-community")
            ["Tom Araya <tom@slayer.com>", "Nicko McBrain <nicko@ironmaiden.com>", "James Hetfield <james@metallica.com>"]
        """

        return self.api.get_collection_authors(collection)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="a{sas}")
    def get_collection_categories(self, collection):
        """
        Returns a list of categories for a given collection.

        Every collection has an identifier (e.g. `ubuntu-community`) that
        we use to refer to the group of accomplishments that form that collection.

        This function returns all categories (without duplicates) for the collection
        passed to it.

        Args:
            * **collection** - (str) the accomplishments collection identifier (e.g. `ubuntu-community`)
        Returns:
            * **(list)** - the list of categories from that collection.
        Example:
            >>> obj.get_collection_categories("ubuntu-community")
            ["Launchpad", "Ask Ubuntu", "Development", . . .]
        """
        return self.api.get_collection_categories(collection)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="v")
    def get_collection_data(self, collection):
        """DOCS NEEDED"""

        return self.api.get_collection_data(collection)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="as")
    def list_accoms(self):
        """
        Returns a list of accomplishment IDs for the all available accomplishments. This includes all accomplishment IDs
        from all collections.

        Args:
            None.
        Returns:
            * **(list)** - the list of accomplishment IDs.
        Example:
            >>> obj.list_accoms()
            ["ubuntu-community/registered-on-launchpad", "ubuntu-community/ubuntu-member", . . .]
        """

        return self.api.list_accoms()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="as")
    def list_trophies(self):
        """
        Returns a list of trophies for the all available accomplishments in accomplishment ID format.

        Args:
            None.
        Returns:
            * **(list)** - the list of accomplishment IDs for all trophies.
        Example:
            >>> obj.list_trophies()
            ["ubuntu-community/registered-on-launchpad", "ubuntu-community/ubuntu-member", . . .]
        """

        return self.api.list_trophies()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="as")
    def list_opportunities(self):
        """
        Returns a list of accomplishment IDs for the all available opportunities. This includes all accomplishment IDs
        from all sets.

        Args:
            None.
        Returns:
            * **(list)** - the list of opportunity accomplishment IDs.
        Example:
            >>> obj.list_opportunities()
            ["ubuntu-community/registered-on-launchpad", "ubuntu-community/ubuntu-member", . . .]
        """

        return self.api.list_opportunities()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="s", out_signature="as")
    def list_depending_on(self, accomID):
        """DOCS NEEDED"""

        return self.api.list_depending_on(accomID)

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="as")
    def list_unlocked(self):
        """
        Returns a list of accomplishment IDs for the all unlocked opportunities. This includes all accomplishment IDs
        from all collections.

        Args:
            None.
        Returns:
            * **(list)** - the list of unlocked opportunity accomplishment IDs.
        Example:
            >>> obj.list_unlocked()
            ["ubuntu-community/registered-on-launchpad", "ubuntu-community/ubuntu-member", . . .]
        """

        return self.api.list_unlocked()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="as")
    def list_unlocked_not_completed(self):
        """
        Returns a list of accomplishment IDs for the all unlocked opportunities that are not completed. This includes all accomplishment IDs
        from all collections.

        Args:
            None.
        Returns:
            * **(list)** - the list of unlocked opportunity accomplishment IDs.
        Example:
            >>> obj.list_unlocked()
            ["ubuntu-community/registered-on-launchpad", "ubuntu-community/ubuntu-member", . . .]
        """

        return self.api.list_unlocked_not_completed()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="as")
    def list_collections(self):
        """
        Returns a list of collections available. Collections are listed in their
        unique formats (e.g. `ubuntu-community`).

        Args:
            None.
        Returns:
            * **(list)** - the list of accomplishment IDs for all trophies.
        Example:
            >>> obj.list_collections()
            ["ubuntu-community", "ubuntu-desktop"]
        """

        return self.api.list_collections()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="aa{sv}")
    def build_viewer_database(self):
        """
        Returns a database of accomplishment information on the system.

        IMPORTANT: you should only ever use this function when you need to as it takes
        some time to process and return the data. It is recommended that you run this once and import
        the data into your own data structure in your client and then only re-run this function when
        you need to.

        Args:
            None
        Returns:
            * **(dict)** - The list of categories from that collection.
        Example:
            >>> obj.build_viewer_database()
            {dbus.String(u'date-completed'): dbus.String(u'2012-07-04 19:18', variant_level=1), dbus.String(u'locked'): dbus.Boolean(False, variant_level=1), dbus.String(u'title'): dbus.String(u'Filed Bug that was Confirmed', variant_level=1), dbus.String(u'collection-human'): dbus.String(u'Ubuntu Community', variant_level=1), dbus.String(u'collection'): dbus.String(u'ubuntu-community', variant_level=1), dbus.String(u'accomplished'): dbus.Boolean(True, variant_level=1), dbus.String(u'iconpath'): dbus.String(u'/home/jono/.cache/accomplishments/trophyimages/ubuntu-community/default.png', variant_level=1), dbus.String(u'id'): dbus.String(u'ubuntu-community/first-bug-confirmed', variant_level=1), dbus.String(u'categories'): dbus.Array([dbus.String(u'QA')], signature=dbus.Signature('s'), variant_level=1)}
        """

        return self.api.build_viewer_database()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="s")
    def get_API_version(self):
        """
        Returns the accomplishments API version for the installed daemon.

        This function is useful when you want to ensure that an accomplishment's API version works with the installed
        daemon.

        Please note: the accomplishment's API references the API and might not match the version of the daemon. As an example, the
        accomplishments API might be 0.2, but the daemon might be version 1.2 and still use the 0.2 accomplishments API version.

        Args:
            None
        Returns:
            * **(str)** - the API version
        Example:
            >>> obj.get_API_version()
            0.2
        """

        return self.api.get_API_version()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="")
    def stop_daemon(self):
        return self.api.stop_daemon()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="")
    def publish_trophies_online(self):
        return self.api.publish_trophies_online()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="")
    def unpublish_trophies_online(self):
        return self.api.unpublish_trophies_online()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="s")
    def get_share_id(self):
        return self.api.get_share_id()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="s")
    def get_share_name(self):
        return self.api.get_share_name()

    @dbus.service.method(dbus_interface='org.ubuntu.accomplishments',
                         in_signature="", out_signature="")
    def create_all_trophy_icons(self):
        return self.api.create_all_trophy_icons()


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

    @dbus.service.signal(dbus_interface='org.ubuntu.accomplishments')
    def accoms_collections_reloaded(self):
        pass
