"""
(c) 2012, Jono Bacon, and the Ubuntu Accomplishments community.

This is the core Ubuntu Accomplishments daemon API.

This file is licensed under the GNU Public License version 3.

If you are interested in contributing improvements or changes to this
program, please see http://wiki.ubuntu.com/Accomplishments for how to
get involved.
"""

import gettext
from gettext import gettext as _
from gettext import ngettext as N_
import ConfigParser
import Image, ImageEnhance
from StringIO import StringIO
import datetime
import getpass
import glob
import gobject
import gpgme
import json
import os
import pwd
import subprocess
import time
import locale
from collections import deque
 
import dbus
import dbus.service

from twisted.internet import defer, reactor
from twisted.internet.protocol import ProcessProtocol
from twisted.python import filepath
from twisted.python import log

import xdg.BaseDirectory

try:
    import pynotify
except ImportError:
    pynotify = None

from ubuntuone.platform.tools import SyncDaemonTool
from ubuntuone.platform.credentials import CredentialsManagementTool
from ubuntuone.couch import auth

import accomplishments
from accomplishments import exceptions
from accomplishments.daemon import dbusapi
from accomplishments.util import get_data_file, SubprocessReturnCodeProtocol
from accomplishments.util.paths import daemon_exec_dir, media_dir, module_dir1, module_dir2, installed, locale_dir

gettext.bindtextdomain('accomplishments-daemon',locale_dir)
gettext.textdomain('accomplishments-daemon')

os.environ["PYTHONPATH"] = "$PYTHONPATH:."
# The directories with accomplishment.* modules, that are being used by scripts,
# may happen to be in a completelly different directory, if the daemon was
# installed using a non-default prefix.
if installed:
    os.environ["PYTHONPATH"] = module_dir1 + ":" + module_dir2 + ":" + os.environ["PYTHONPATH"]

LOCAL_USERNAME = getpass.getuser()
SCRIPT_DELAY = 900
ONLINETROPHIESHOST = "213.138.100.229:8000"

#flags used for scripts_state
NOT_RUNNING = 0
RUNNING = 1

# XXX the source code needs to be updated to use Twisted async calls better:
# grep the source code for any *.asyncapi.* references, and if they return
# deferreds, adjust them to use callbacks
class AsyncAPI(object):
    """
    This class simply organizes all the Twisted calls into a single location
    for better readability and separation of concerns.
    """
    def __init__(self, parent):
    
        self.parent = parent
        
        # The following variable represents state of scripts.Its state 
        # can be either RUNNING or NOT_RUNNING.
        # The use of this flag is to aviod running several instances of 
        # start_scriptrunner, which might result in undefined, troubleful
        # behavior. The flags are NOT_RUNNING by default, and are set to
        # RUNNING when the start_scriptrunner runs, and back to
        # NOT_RUNNING when it exits. This way, if the function is already
        # processing scripts, another calls will abort, having checked that
        # this flag is set to RUNNING.
        self.scripts_state = NOT_RUNNING

    @staticmethod
    def run_a_subprocess(command):
        # Commented out this debug message, as it creates lots of junk, 
        # and is not needed for common troubleshooting
        # log.msg("Running subprocess command: " + str(command))
        pprotocol = SubprocessReturnCodeProtocol()
        reactor.spawnProcess(pprotocol, command[0], command, env=os.environ)
        return pprotocol.returnCodeDeferred

    @defer.inlineCallbacks
    def verify_ubuntu_one_account(self):
        # check if this machine has an Ubuntu One account
        log.msg("Check if this machine has an Ubuntu One account...")

        tool = CredentialsManagementTool()
        creds = yield tool.register()
        
        if len(creds) > 1:
            log.msg("...Yes.")
            self.parent.has_u1 = True
            self.parent.service.ubuntu_one_account_ready()
        else:
            log.msg("...No.")
            log.msg(u1auth_response)
            self.parent.has_u1 = False

    # XXX let's rewrite this to use deferreds explicitly
    @defer.inlineCallbacks
    def register_trophy_dir(self, trophydir):
        """
        Creates the Ubuntu One share for the trophydir and offers it to the
        server. Returns True if the folder was successfully shared, False if
        not.
        """
        timeid = str(time.time())
        log.msg("Registering Ubuntu One share directory: " + trophydir)

        folder_list = yield self.parent.sd.get_folders()
        folder_is_synced = False
        for folder in folder_list:
            if folder["path"] == trophydir:
                folder_is_synced = True
                break
        if not folder_is_synced:
            # XXX let's breack this out into a separate sync'ing method
            log.msg(
                "...the '%s' folder is not synced with the Matrix" % trophydir)
            log.msg("...creating the share folder on Ubuntu One")
            self.parent.sd.create_folder(trophydir)

            success_filter = lambda info: info["path"] == trophydir
            info = yield self.parent.sd.wait_for_signals(
                signal_ok='FolderCreated', success_filter=success_filter)

            self.parent.sd.offer_share(
                trophydir, self.parent.matrix_username, LOCAL_USERNAME + " Trophies Folder"
                + " (" + timeid + ")", "Modify")
            log.msg(
                "...share has been offered (" + trophydir + "" + ", "
                + self.parent.matrix_username + ", " + LOCAL_USERNAME + ")")
            return

        log.msg("...the '%s' folder is already synced" % trophydir)
        # XXX put the following logic into a folders (plural) sharing method
        log.msg("... now checking whether it's shared")
        shared_list = yield self.parent.sd.list_shared()
        folder_is_shared = False
        shared_to = []
        for share in shared_list:
            # XXX let's break this out into a separate share-tracking method
            if share["path"] == trophydir:
                log.msg("...the folder is already shared.")
                folder_is_shared = True
                shared_to.append("%s (%s)" % (
                    share["other_visible_name"], share["other_username"]))
        if not folder_is_shared:
            # XXX let's break this out into a separate folder-sharing method
            log.msg("...the '%s' folder is not shared" % trophydir)
            self.parent.sd.offer_share(
                trophydir, self.parent.matrix_username, LOCAL_USERNAME + " Trophies Folder"
                + " (" + timeid + ")", "Modify")
            log.msg("...share has been offered (" + trophydir + "" + ", "
                + self.parent.matrix_username + ", " + LOCAL_USERNAME + ")")
            log.msg("...offered the share.")
            return
        else:
            log.msg("The folder is shared, with: %s" % ", ".join(
                shared_to))
            return

        self.parent._refresh_share_data()

    # XXX let's rewrite this to use deferreds explicitly
    @defer.inlineCallbacks
    def start_scriptrunner(self):

        # More info on scripts_state can be found in __init__
        if self.scripts_state is RUNNING:
            # Aborting this call - scriptrunner is already working.
            return

        self.scripts_state = RUNNING

        uid = os.getuid()
        # Is the user currently logged in and running a gnome session?
        # XXX use deferToThread
        username = pwd.getpwuid(uid).pw_name
        try:
            # XXX since we're using Twisted, let's use it here too and use the
            # deferred-returning call
            proc = subprocess.check_output(
                ["pgrep", "-u", username, "gnome-session"]).strip()
        except subprocess.CalledProcessError:
            # user does not have gnome-session running or isn't logged in at
            # all
            log.msg("No gnome-session process for user %s" % username)
            self.scripts_state = NOT_RUNNING #unmarking to avoid dead-lock
            return
        # XXX this is a blocking call and can't be here if we want to take
        # advantage of deferreds; instead, rewrite this so that the blocking
        # call occurs in a separate thread (e.g., deferToThread)
        fp = open("/proc/%s/environ" % proc)
        try:
            envars = dict(
                [line.split("=", 1) for line in fp.read().split("\0")
                if line.strip()])
        except IOError:
            # user does not have gnome-session running or isn't logged in at
            # all
            log.msg("No gnome-session environment for user %s" % username)
            self.scripts_state = NOT_RUNNING #unmarking to avoid dead-lock
            return
        fp.close()

        # XXX use deferToThread
        os.seteuid(uid)

        required_envars = ['DBUS_SESSION_BUS_ADDRESS']
        env = dict([kv for kv in envars.items() if kv[0] in required_envars])
        # XXX use deferToThread
        oldenviron = os.environ
        os.environ.update(env)
        # XXX note that for many of these deferredToThread changes, we can put
        # them all in a DeferredList and once they're all done and we have the
        # results for all of them, a callback can be fired to continue.

        # XXX this next call, a DBus check, happens in the middle of this
        # method; it would be better if this check was done at a higher level,
        # for instance, where this class is initiated: if the daemon isn't
        # registered at the time of instantiation, simply abort then instead of
        # making all the way here and then aborting. (Note that moving this
        # check to that location will also eliminate an obvious circular
        # import.)
        if not dbusapi.daemon_is_registered():
            return

        # XXX all parent calls should be refactored out of the AsyncAPI class
        # to keep the code cleaner and the logic more limited to one particular
        # task

        queuesize = len(self.parent.scripts_queue)

        log.msg("--- Starting Running Scripts - %d items on the queue ---" % (queuesize))
        timestart = time.time()
        if not self.parent.test_mode:
            self.parent.service.scriptrunner_start()

        while queuesize > 0:
            accomID = self.parent.scripts_queue.popleft()
            log.msg("Running %s, left on queue: %d" % (accomID, queuesize-1))

            # First ensure that the acccomplishemt has not yet completed.
            # It happens that the .asc file is present, but we miss the
            # signal it triggers - so here we can re-check if it is not
            # present.
            if self.parent._check_if_acc_is_completed(accomID):
                self.parent.accomplish(accomID)
            else:
                # Okay, this one hasn't been yet completed.
                # Run the acc script and determine exit code.
                scriptpath = self.parent.get_acc_script_path(accomID)
                if scriptpath is None:
                    log.msg("...No script for this accomplishment, skipping")
                else:
                    # There is a script for this accomplishmend, so run it
                    exitcode = yield self.run_a_subprocess([scriptpath])
                    if exitcode == 0:
                        log.msg("...Accomplished")
                        self.parent.accomplish(accomID)
                    elif exitcode == 1:
                        log.msg("...Not Accomplished")
                    elif exitcode == 2:
                        log.msg("....Error")
                    elif exitcode == 4:
                        log.msg("...Could not get extra-information")
                    else:
                        log.msg("...Error code %d" % exitcode)

            # New queue size is determined on the very end, since accomplish()
            # might have added something new to the queue.
            queuesize = len(self.parent.scripts_queue)


        log.msg("The queue is now empty - stopping the scriptrunner.")

        os.environ = oldenviron

        # XXX eventually the code in this method will be rewritten using
        # deferreds; as such, we're going to have to be more clever regarding
        # timing things...
        timeend = time.time()
        timefinal = round((timeend - timestart), 2)

        log.msg(
            "--- Emptied the scripts queue in %.2f seconds---" % timefinal)
        if not self.parent.test_mode:
            self.parent.service.scriptrunner_finish()

        self.scripts_state = NOT_RUNNING

class Accomplishments(object):
    """The main accomplishments daemon.

    No D-Bus required, so that it can be used for testing.
    """
    def __init__(self, service, show_notifications=None, test_mode=False):
        self.accomplishments_installpaths = None
        self.trophies_path = None
        self.has_u1 = False
        self.has_verif = None
        
        self.matrix_username = ""
        self.share_found = False
        self.share_id = ""
        self.share_name = ""
        
        self.lang = locale.getdefaultlocale()[0]
        
        # use this to override the language for testing
        #self.lang = "pt_BR"
        self.accomlangs = []
        self.service = service
        self.asyncapi = AsyncAPI(self)

        self.scripts_queue = deque()
        self.test_mode = test_mode

        try:
            rootdir = os.environ['ACCOMPLISHMENTS_ROOT_DIR']
            self.dir_config = os.path.join(
                rootdir, "accomplishments", ".config", "accomplishments")
            self.dir_data = os.path.join(
                rootdir, "accomplishments", ".local", "share", "accomplishments")
            self.dir_cache = os.path.join(
                rootdir, "accomplishments", ".cache", "accomplishments")
        except KeyError:
            self.dir_config = os.path.join(
                xdg.BaseDirectory.xdg_config_home, "accomplishments")
            self.dir_data = os.path.join(
                xdg.BaseDirectory.xdg_data_home, "accomplishments")
            self.dir_cache = os.path.join(
                xdg.BaseDirectory.xdg_cache_home, "accomplishments")

        if not os.path.exists(self.dir_config):
            os.makedirs(self.dir_config)

        if not os.path.exists(self.dir_data):
            os.makedirs(self.dir_data)

        if not os.path.exists(self.dir_cache):
            os.makedirs(self.dir_cache)

        self.dir_autostart = os.path.join(
            xdg.BaseDirectory.xdg_config_home, "autostart")

        print str("------------------- Ubuntu Accomplishments Daemon "
            "- "+ str(datetime.datetime.now()) +" -------------------")

        self._load_config_file()

        print str("Accomplishments install paths: " + self.accomplishments_installpaths)
        print str("Trophies path: " + self.trophies_path)

        self.show_notifications = show_notifications
        log.msg("Connecting to Ubuntu One")
        if not self.test_mode:
            self.sd = SyncDaemonTool()
        else:
            log.msg("Test mode enabled, not connecting to SyncDaemonTool()")
            self.sd = None

        self.reload_accom_database()

        if not self.test_mode:
            self.sd.connect_signal("DownloadFinished", self._process_recieved_asc_file)

        self._create_all_trophy_icons()
        
        self._refresh_share_data()

    def get_media_file(self, media_file_name):
        #log.msg("MEDIA_FILE_NAME:")
        #log.msg(media_file_name)
        #log.msg("MEDIA_DIR:")
        #log.msg(media_dir)
        media_filename = os.path.join(media_dir, media_file_name)
        #log.msg("MEDIA_FILENAME:")
        #log.msg(media_filename)

        if not os.path.exists(media_filename):
            return None

        final = "file:///" + media_filename
        return final

    def _create_all_trophy_icons(self):
        """Iterate through each of the accomplishments on the system
        and generate all of the required icons that we provide to
        clients."""
        cols = self.list_collections()

        for col in cols:
            col_imagespath = os.path.join(self.accDB[col]['base-path'],"trophyimages")
            cache_trophyimagespath = os.path.join(
                self.dir_cache, "trophyimages", col)
            lock_image_path = os.path.join(media_dir, "lock.png")
            if not os.path.exists(cache_trophyimagespath):
                os.makedirs(cache_trophyimagespath)
            
            # First, delete all cached images:
            cachedlist=glob.glob(cache_trophyimagespath + "/*")
            for c in cachedlist:
                os.remove(c)
            
            mark = Image.open(lock_image_path)
            for root, dirs, files in os.walk(col_imagespath):
                for name in files:
                    try:
                        im = Image.open(os.path.join(root, name))
                        filename = os.path.join(cache_trophyimagespath, name)
                        filecore = os.path.splitext(filename)[0]
                        filetype = os.path.splitext(filename)[1]

                        im.save(filename)
                        
                        # Opacity set to 1.0 until we figure out a better way of
                        # showing opportunities
                        reduced = self._create_reduced_opacity_trophy_icon(im, 1.0)
                        reduced.save(filecore + "-opportunity" + filetype)

                        if im.mode != 'RGBA':
                            im = im.convert('RGBA')
                        layer = Image.new('RGBA', im.size, (0,0,0,0))
                        position = (
                            im.size[0] - mark.size[0], im.size[1] - mark.size[1])
                        layer.paste(mark, position)
                        img = Image.composite(layer, reduced, layer)
                        img.save(filecore + "-locked" + filetype)
                        
                    except Exception, (msg):
                        log.msg(msg)
            

    def _create_reduced_opacity_trophy_icon(self, im, opacity):
        """Returns an image with reduced opacity."""
        
        assert opacity >= 0 and opacity <= 1
        if im.mode != 'RGBA':
            im = im.convert('RGBA')
        else:
            im = im.copy()
        alpha = im.split()[3]
        alpha = ImageEnhance.Brightness(alpha).enhance(opacity)
        im.putalpha(alpha)
        return im

    def get_config_value(self, section, item):
        """Return a configuration value from the .accomplishments file"""
        log.msg(
            "Returning configuration values for: %s, %s" % (section, item))
        config = ConfigParser.RawConfigParser()
        cfile = self.dir_config + "/.accomplishments"
        config.read(cfile)

        if config.has_option(section, item):
            if section == "config" and item == "has_u1":
                item = config.getboolean(section, item)
                return item
            elif section == "config" and item == "has_verif":
                item = config.getboolean(section, item)
                return item
            elif section == "config" and item == "daemon_sessionstart":
                item = config.getboolean(section, item)
                return item
            else:
                item = config.get(section, item)
                return item
        else:
            return "NoOption"

    def verify_ubuntu_one_account(self):
        self.asyncapi.verify_ubuntu_one_account()

    def write_config_file_item(self, section, item, value):
        """Set a configuration value in the .accomplishments file"""
        log.msg(
            "Set configuration file value in '%s': %s = %s" % (section, item,
            value))
        config = ConfigParser.RawConfigParser()
        cfile = self.dir_config + "/.accomplishments"

        config.read(cfile)
        if config.has_section(section) is False:
            config.add_section(section)
        else:
            config.set(section, item, value)

        # Writing our configuration file to 'example.cfg'
        with open(cfile, 'wb') as configfile:
            config.write(configfile)

        self._load_config_file()

    def _write_config_file(self):
        """Write the values held in various configuration state variables
        to the main daemon configuration file, which should be located
        in ~/.config/accomplishments/.accomplishments."""
        
        log.msg("Writing the configuration file")
        config = ConfigParser.RawConfigParser()
        cfile = self.dir_config + "/.accomplishments"

        # The following sets self.has_u1
        self.verify_ubuntu_one_account()
        
        config.add_section('config')

        config.set('config', 'has_u1', self.has_u1)
        config.set('config', 'has_verif', self.has_verif)
        config.set('config', 'accompath', self.accomplishments_installpaths)
        config.set('config', 'trophypath', self.trophies_path)

        with open(cfile, 'wb') as configfile:
        # Writing our configuration file to 'example.cfg'
            config.write(configfile)

        log.msg("...done.")


    def _load_config_file(self):
        """Load the main configuration file for the daemon. This should be
        located in ~/.config/accomplishments/.accomplishments and it provides
        a ConfigParser INI-style list of values."""

        config = ConfigParser.RawConfigParser()
        cfile = os.path.join(self.dir_config, ".accomplishments")

        if config.read(cfile):
            log.msg("Loading configuration file: " + cfile)
            if config.get('config', 'accompath'):
                self.accomplishments_installpaths = config.get('config', 'accompath')
                log.msg(
                    "...setting accomplishments install paths to: "
                    + self.accomplishments_installpaths)
            if config.get('config', 'trophypath'):
                log.msg(
                    "...setting trophies path to: "
                    + config.get('config', 'trophypath'))
                self.trophies_path = config.get('config', 'trophypath')
            if config.get('config', 'has_u1'):
                self.has_u1 = config.getboolean('config', 'has_u1')
            if config.get('config', 'has_verif'):
                self.has_verif = config.getboolean('config', 'has_verif')
            if config.has_option('config','staging') and config.get('config', 'staging'):
                self.matrix_username = "openiduser204307" # staging ID
            else:
                self.matrix_username = "openiduser155707" # production ID

        else:
            # setting accomplishments path to the system default
            home = os.path.expanduser("~/accomplishments")
            accompath = home + ":" + "/usr/share/accomplishments"
            log.msg("Configuration file not found...creating it!")

            self.has_verif = False
            self.accomplishments_installpaths = accompath
            log.msg(
                "...setting accomplishments install paths to: "
                + self.accomplishments_installpaths)
            log.msg("You can set this to different locations in your config file.")
            self.trophies_path = os.path.join(self.dir_data, "trophies")
            log.msg("...setting trophies path to: " + self.trophies_path)

            if not os.path.exists(self.trophies_path):
                os.makedirs(self.trophies_path)

            self._write_config_file()

    def _refresh_share_data(self):
        if not self.test_mode:
            l = self.sd.list_shared()
            l.addCallback(self._complete_refreshing_share_data)
        
    def _complete_refreshing_share_data(self,shares):
        matchingshares = []

        for s in shares:
            if s["other_username"] == self.matrix_username:
                if s["subscribed"] == "True":
                    matchingshares.append( { "name" : s["name"], "share_id" : s["volume_id"] } )

        if len(matchingshares) > 1:
            log.msg("Could not find unique active share.")
            self.share_found = False
        else:
            self.share_name = matchingshares[0]["name"]
            self.share_id = matchingshares[0]["share_id"]
            self.share_found = True
    
    def get_share_name(self):
        if self.share_found:
            return self.share_name
        else:
            return ""
    def get_share_id(self):
        if self.share_found:
            return self.share_id
        else:
            return ""
    
    def publish_trophies_online(self):
        if self.share_found:
            trophydir = self.get_config_value("config", "trophypath")
            webviewfile = open(os.path.join(trophydir, "WEBVIEW"), 'w')
            string = " "
            webviewfile.write(string)
            url = "http://" + ONLINETROPHIESHOST + "/user/addshare?share_name=" + self.share_name + "&share_id=" + self.share_id
            
            self.service.publish_trophies_online_completed(url)
            return url
        else:  
            log.msg("Unable to publish trophies - no share found.")
            return ""

    def unpublish_trophies_online(self):
        trophydir = self.get_config_value("config", "trophypath")
        os.remove(os.path.join(trophydir, "WEBVIEW"))

    def get_all_extra_information(self):
        """
        This function is used to retrieve all extra-information data, along with its name, description - as provided by the accomplishment collection - and it's current value.
        
        Returns:
            * **array(dict(str:str))** - A list of all extra-information items used by currently installed accomplishments collections. Note that a single item can be present several times, if more than one collection uses the same extra-information data (see example).
            * The list of fields in returned dictionaries:
                * *collection* - the name of colletion that uses this extra-information (e.g. ubuntu-community)
                * *needs-information* - the name of extra-information data bit (e.g. launchpad-email)
                * *label* - the user-readable name of this extra-information field. It is provided by the **collection** so may vary. It should be translated according to user's locale.
                * *description* - an user-readable, one line long description for this extra-information item. It is also provided by the **collection**, and a translated string is provided, if available.
                * *example* - a example value for this extra-information, provided by the collection (e.g. launchpad-email might have an example: foo@bar.com). If no example is provided, it will be an empty string.
                * *regex* - a regular expression used to check whether the value of this extra-information field uses a correct format. If collection provides no regexp, it will be an empty string.
                * *value* - the current value of this field, as set by the user. It will be the same for all collections that use this extra-information item.
        Example:
            >>> acc.get_all_extra_information()
            [{"collection" : "ubuntu-community", "needs-information" : "launchpad-email", "label" : "Launchpad e-mail", "description" : "The e-mail address you use to log in to Launchpad", "example" : "foo@bar.com", "regex" : "", "value" : "someuser@somehost.org"},
             {"collection" : "ubuntu-italiano", "needs-information" : "launchpad-email", "label" : "Launchpad e-mail", "description" : "Type in your LP e-mail, amigo!", "example" : "some@email.com", "regex" : "", "value" : "someuser@somehost.org"},
             {"collection" : "ubuntu-community", "needs-information" : "askubuntu-user-url", "label" : "AskUbuntu user profile URL", "description" : "The URL of your AskUbuntu usr profile page", "example" : "http://askubuntu.com/users/42/nick", "regex" : "", "value" : ""}]
        """
        # get a list of all accomplishments
        accomplishments = self.list_accomplishments()
        
        infoneeded = []
        # and prepend the path to the directory, where all extra-information 
        # is stored [like: ~/.local/share/accomplishments/trophies/.extrainformation/]
        trophyextrainfo = os.path.join(
            self.trophies_path, ".extrainformation/")

        # in case this directory does not exist, create it 
        # this may happen if user hadn't yet set any ExtraInformation field
        if not os.path.isdir(trophyextrainfo):
            os.makedirs(trophyextrainfo)

        # now, for each accomplishment file that is available...
        for acc in accomplishments:
            # get the path to the directory of accomplishments set's
            # "extrainformation" dir - it is useful, because it contains
            # translated labels and descriptions
            accomextrainfo = os.path.join(self.accDB[acc]['base-path']
                , "extrainformation")
                
            # a temporary variable, representing a single entry of the list this function returns
            d = {}
            
            # Get collection name from accomOD
            collection = self._coll_from_accomID(acc)
            
            ei = self.get_acc_needs_info(acc)
            if len(ei) is not 0:
            
                # For each needed piece of information:
                for i in ei:
                    label = self.accDB[collection]['extra-information'][i]['label']
                    desc = self.accDB[collection]['extra-information'][i]['description']
                    example = self.accDB[collection]['extra-information'][i].get('example')
                    if example is None:
                        example = ''
                    regex = self.accDB[collection]['extra-information'][i].get('regex')
                    if regex is None:
                        regex = ''
                    # we also need to know whether user has already set this item's value.
                    # to do this, simply check whether trophies/.extrainformation/<item> file exists.
                    try:
                        valuefile = open(os.path.join(trophyextrainfo,i))
                        # if we got here without an exception, it means that the file exists
                        # so, we can read it's value
                        value = valuefile.readline()
                        value = value.rstrip() # get rid of the tailing newline
                        # and build up the dictionary of all data for a single ExtraInformation field
                        d = {
                            "collection" : collection,
                            "needs-information" : i,
                            "label" : label,
                            "description" : desc,
                            "example" : example,
                            "regex" : regex,
                            "value" : value}
                    except IOError as e:
                        # we got an exception, so it seems that the file is not present - we'll use "" as the value, to indicate that it's empty
                        d = {
                            "collection" : collection,
                            "needs-information" : i,
                            "label" : label,
                            "description" : desc,
                            "example" : example,
                            "regex" : regex,
                            "value" : ""}

                    # since the collected all data related to this particular ExtraInformation field, append it to the list
                    infoneeded.append(d)

        # at this moment the infoneeded list will be ready, but full of duplicates,
        # for the items have been added multiple times, if they are mentioned in more then one .accomplishment file
        final = []
        for x in infoneeded:   #for each item in the original list...
            if x not in final: #...add it to the outputted list only if it hadn't been added yet.
                final.append(x)

        return final

    def get_all_extra_information_required(self):
        """
        This function does pretty much the same as get_all_extra_information() , but it filters out entries that have no value set. This way it can be easily used to get a list of all extra-information that user still has to provide.
        
        Returns:
            * **array(dict(str:str))** - A list of all extra-information items used by currently installed accomplishments collections **that are not yet set**. Details are the same as in get_all_extra_information()
        
        Example:
            >>> acc.get_all_extra_information_required()
            [{"collection" : "ubuntu-community", "needs-information" : "askubuntu-user-url", "label" : "AskUbuntu user profile URL", "description" : "The URL of your AskUbuntu usr profile page", "example" : "http://askubuntu.com/users/42/nick", "regex" : "", "value" : ""}]
        
        """
        #fetch a full list of ExtraInformation
        data = self.get_all_extra_information()
        #now we need to unsort the data just to output these entries, that have value == ""
        #this way we can return a list of ExtraInformation fields, that have not been write_config_file_item
        result = []
        for i in data: #for each ExtraInformation in the full list
            if not i['value']: #if the value string is empty, so this ExtraInformation field have not been yet set
                i.pop('value') #remove the 'value' field (it's empty anyway)
                result.append(i) #add this entry to the resulting list
            #do not add these fields, that have some value
            
        return result

    def create_extra_information_file(self, item, data):
        """Does exactly the same as write_extra_information_file(), but it does not
           overwrite any existing data"""
           
        # XXX this should be removed as we are using write_extra_information_file
        log.msg(
            "Creating Extra Information file: %s, %s" % (item, data))
        extrainfodir = os.path.join(self.trophies_path, ".extrainformation/")

        if not os.path.isdir(extrainfodir):
            os.makedirs(extrainfodir)
        try:
            open(os.path.join(extrainfodir, item)) #if the file already exists, do not overwrite it
            pass
        except IOError as e:
            f = open(os.path.join(extrainfodir, item), 'w')
            f.write(data)
            f.close()

    def _process_recieved_asc_file(self, path, info):
        log.msg("Trophy signature recieved...")
        log.msg("Processing signature: " + path)

        if path.startswith(self.trophies_path) and path.endswith(".asc"):
            valid = self._get_is_asc_correct(path)

            if not valid:
                log.msg("WARNING: invalid .asc signature recieved from the server!")
        
            if valid == True:
                accomID = path[len(self.trophies_path)+1:-11]
                self.service.trophy_received(accomID)
                self._display_accomplished_bubble(accomID)
                self._display_unlocked_bubble(accomID)
                # Mark as completed and get list of new opportunities
                just_unlocked = self._mark_as_completed(accomID)
                self.run_scripts(just_unlocked)
            
    def write_extra_information_file(self, item, data):
        log.msg(
            "Saving Extra Information file: %s, %s" % (item, data))
        extrainfodir = os.path.join(self.trophies_path, ".extrainformation/")

        if not os.path.isdir(extrainfodir):
            os.makedirs(extrainfodir)
        
        if data:
            f = open(os.path.join(extrainfodir, item), 'w') #will trunkate the file, in case it exist
            f.write(data)
            f.close()
        else: 
            #file would be empty, remove it instead
            os.remove(os.path.join(extrainfodir, item))
            
    def invalidate_extra_information(self,extrainfo):
        """
        .. warning::
            This function is deprecated.
            
        This function was used to remove all trophies that were accomplished using given extra-information. For example, if I used launchpad-email userA@mail.com and then switched to userB@mail.com, it was useful to call this function to remove all trophies that were awarded to userA@mail.com. However, since 0.2 throphies may not be deleted automatically under no circumstances, this function **does nothing** now.
        
        Args: 
            * **extrainfo** - (str) the extra-information field that is no more valid (e.g. launchpad-email)
        """
        pass
            
    def get_extra_information(self, coll, item):
        """
        .. note::
            This function is particularly sensitive - accomplishment scripts use it to fetch credentials they need.
            
        This function returns extra-information's value, as set by user. It also provides it with translated label of this extra-information.
        
        Args:
            * **coll** - (str) the name of collection that needs this item. Depending on this, different label may be returned, if collections provide different extrainformation details.
            * **item** - (str) the name of requested item.
            
        Returns:
            * **dict(str:str)** - output is wrapped in a dictionary:
                - *item* - the value of this item. (e.g. ``"askubuntu-user-url" : "askubuntu.com/users/12345/nickname"``).
                - **label** - a translated label, as provided by chosen collection.
                
        Example:
            >>> acc.get_extra_information("ubuntu-community","launchpad-email")
            {"launchpad-email" : "user@host.org", "label" : "Adres e-mail uzywany do logowania w portalu Launchpad"}
            >>> acc.get_extra_information("ubuntu-italiano","launchpad-email")
            {"launchpad-email" : "user@host.org", "label" : "E-mail address used to log into Launchpad"}
        In above example user has an outdated ubuntu-italiano collection, and it doesn't yet have a Polish label - therefore it differs from previous call.
            >>> acc.get_extra_information("ubuntu-community","askubuntu-user-url")
            {"askubuntu-user-url" : "http://askubuntu.com/users/12345/nickname", "label" : "URL of your AskUbuntu profile page"}
        """
        extrainfopath = os.path.join(self.trophies_path, ".extrainformation/")
        authfile = os.path.join(extrainfopath, item)
        
        if not self.get_collection_exists(coll):
            log.msg("No such collection:" + coll)
            return None
        
        label = self.accDB[coll]['extra-information'][item]['label']
        
        try:
            f = open(authfile, "r")
            data = f.read()
            final = [{item : data, "label" : label}]
        except IOError as e:
            #print "No data."
            final = [{item : "", "label" : label}]
        return final
		
    # =================================================================
        
    def reload_accom_database(self):
        """
        This is the function that builds up the *accDB* accomplishments database. It scans all accomplishment installation directories (as set in the config file), looks for all installed collections, and caches all accomplishments' data in memory. If a translated .accomplishment file is available, it's contents are loaded instead.
        
        It also groups collection categories, authors, finds accomplishment script paths, and counts accomplishments in collections.
        
        All results are stored in an internal variable, *self.accDB*. They can be accessed afterwards using get_acc_* functions.
        
        Running this function also calls _update_all_locked_and_completed_statuses(), which completes initialising the *accDB*, as it fills in it's "completed" and "locked" fields.
        
        .. note::
            There is no need for clients to run this method manually when the daemon is started - this function is called by this class' __init__.
        
        Args:
            *None.*
            
        Returns:
            * Nothing.
        
        """
        # First, clear the database.
        self.accDB = {}
        # Get the list of all paths where accomplishments may be
        # installed...
        installpaths = self.accomplishments_installpaths.split(":")
        for installpath in installpaths:
            # Look for all accomplishment collections in this path
            path = os.path.join(installpath,'accomplishments')
            if not os.path.exists(path):
                continue
            
            collections = os.listdir(path)
            for collection in collections:
                # For each collection...
                if collection in self.accDB:
                    # This collection has already been loaded from another install path!
                    continue
                
                collpath = os.path.join(path,collection)
                aboutpath = os.path.join(collpath,'ABOUT')
                
                # Load data from ABOUT file
                cfg = ConfigParser.RawConfigParser()
                cfg.read(aboutpath)
                
                if not (cfg.has_option("general","langdefault") and cfg.has_option("general","name")):
                    print aboutpath
                    raise LookupError("Accomplishment collection with invalid ABOUT file ")
                
                langdefault = cfg.get("general","langdefault")
                collectionname = cfg.get("general","name")
                
                collauthors = set()
                collcategories = {}
                
                langdefaultpath = os.path.join(collpath,langdefault)
                setsslist = os.listdir(langdefaultpath)
                accno = 0
                for accomset in setsslist:
                    if accomset[-15:] == '.accomplishment':
                        # this is an ungroped accomplishment file
                        accompath = os.path.join(langdefaultpath,accomset)
                        accomcfg = ConfigParser.RawConfigParser()
                        # check if there is a translated version...
                        translatedpath = os.path.join(os.path.join(collpath,self.lang),accomset)
                        if os.path.exists(translatedpath):
                            # yes, so use the translated file
                            accomcfg.read(translatedpath)
                            langused = self.lang
                        else:
                            # no. maybe there is a shorter language code?
                            translatedpath = os.path.join(os.path.join(collpath,self.lang.split("_")[0]),accomset)
                            if os.path.exists(translatedpath):
                                accomcfg.read(translatedpath)
                                langused = self.lang.split("_")[0]
                            else:
                                # no. fallback to default one
                                accomcfg.read(accompath)
                                langused = langdefault
                        accomdata = dict(accomcfg._sections["accomplishment"])
                        accomID = collection + "/" + accomset[:-15]
                        if 'author' in accomdata:
                            collauthors.add(accomdata['author'])
                        del accomdata['__name__']
                        accomdata['set'] = ""
                        accomdata['collection'] = collection
                        accomdata['type'] = "accomplishment"
                        accomdata['lang'] = langused
                        accomdata['base-path'] = collpath
                        accomdata['script-path'] = os.path.join(installpath,os.path.join('scripts',os.path.join(collection,accomset[:-15] + ".py")))
                        if 'category' in accomdata:
                            cats = accomdata['category'].split(",")
                            categories = []
                            accomdata['categories'] = []
                            for cat in cats:
                                catsplitted = cat.rstrip().lstrip().split(":")
                                accomdata['categories'].append(cat.rstrip().lstrip())
                                if catsplitted[0] in collcategories:
                                    pass
                                else:
                                    collcategories[catsplitted[0]] = []
                                if len(catsplitted) > 1:
                                    # category + subcategory
                                    if catsplitted[1] not in collcategories[catsplitted[0]]:
                                        collcategories[catsplitted[0]].append(catsplitted[1])
                            del accomdata['category']
                        else:
                            accomdata['categories'] = []
                        self.accDB[accomID] = accomdata
                        accno = accno + 1
                    else:
                        # this is indeed a set!
                        setID = collection + ":" + accomset
                        setdata = {'type':"set",'name':accomset}
                        self.accDB[setID] = setdata
                        setdir = os.path.join(langdefaultpath,accomset)
                        accomfiles = os.listdir(setdir)
                        for accomfile in accomfiles:
                            # For each accomplishment in this set...
                            accompath = os.path.join(langdefaultpath,os.path.join(accomset,accomfile))
                            accomcfg = ConfigParser.RawConfigParser()
                            # check if there is a translated version...
                            translatedpath = os.path.join(os.path.join(collpath,self.lang),os.path.join(accomset,accomfile))
                            if os.path.exists(translatedpath):
                                # yes, so use the translated file
                                accomcfg.read(translatedpath)
                                langused = self.lang
                            else:
                                # no. maybe there is a shorter language code?
                                translatedpath = os.path.join(os.path.join(collpath,self.lang.split("_")[0]),os.path.join(accomset,accomfile))
                                if os.path.exists(translatedpath):
                                    accomcfg.read(translatedpath)
                                    langused = self.lang.split("_")[0]
                                else:
                                    # no. fallback to default one
                                    accomcfg.read(accompath)
                                    langused = langdefault
                            accomdata = dict(accomcfg._sections["accomplishment"])
                            accomID = collection + "/" + accomfile[:-15]
                            if 'author' in accomdata:
                                collauthors.add(accomdata['author'])
                            accomdata['type'] = "accomplishment"
                            del accomdata['__name__']
                            accomdata['set'] = accomset
                            accomdata['collection'] = collection
                            accomdata['lang'] = langused
                            accomdata['base-path'] = collpath
                            accomdata['script-path'] = os.path.join(installpath,os.path.join('scripts',os.path.join(collection,os.path.join(accomset,accomfile[:-15] + ".py"))))
                            if 'category' in accomdata:
                                cats = accomdata['category'].split(",")
                                categories = []
                                accomdata['categories'] = []
                                for cat in cats:
                                    catsplitted = cat.rstrip().lstrip().split(":")
                                    accomdata['categories'].append(cat.rstrip().lstrip())
                                    if catsplitted[0] in collcategories:
                                        pass
                                    else:
                                        collcategories[catsplitted[0]] = []
                                    if len(catsplitted) > 1:
                                        # category + subcategory
                                        if catsplitted[1] not in collcategories[catsplitted[0]]:
                                            collcategories[catsplitted[0]].append(catsplitted[1])
                                del accomdata['category']
                            else:
                                accomdata['categories'] = []
                            self.accDB[accomID] = accomdata
                            accno = accno + 1
                            
                # Look for extrainformation dir
                extrainfodir = os.path.join(collpath,"extrainformation")
                extrainfolist = os.listdir(extrainfodir)
                extrainfo = {}
                for extrainfofile in extrainfolist:
                    extrainfopath = os.path.join(extrainfodir,extrainfofile)
                    eicfg = ConfigParser.RawConfigParser()
                    eicfg.read(extrainfopath)

                    if eicfg.has_option("label",self.lang):
                        label = eicfg.get("label",self.lang)
                    elif eicfg.has_option("label",self.lang.split("_")[0]):
                        label = eicfg.get("label",self.lang.split("_")[0])
                    else:
                        label = eicfg.get("label",langdefault)

                    if eicfg.has_option("description",self.lang):
                        description = eicfg.get("description",self.lang)
                    elif eicfg.has_option("description",self.lang.split("_")[0]):
                        description = eicfg.get("description",self.lang.split("_")[0])
                    else:
                        description = eicfg.get("description",langdefault)
                        
                    if eicfg.has_option("example", self.lang):
                        example = eicfg.get("example", self.lang)
                    elif eicfg.has_option("example", self.lang.split("_")[0]):
                        example = eicfg.get("example", self.lang.split("_")[0])
                    elif eicfg.has_option("example", langdefault):
                        example = eicfg.get("example", langdefault)
                    else:
                        example = None
                        
                    if eicfg.has_option("regex", "value"):
                        regex = eicfg.get("regex", "value")
                    else:
                        regex = None
                        
                    extrainfo[extrainfofile] = {
                            'label': label,
                            'description': description,
                            'example': example,
                            'regex': regex,
                            }
                
                # Store data about this colection
                collectiondata = {'langdefault':langdefault,'name':collectionname, 'acc_num':accno, 'type':"collection", 'base-path': collpath, 'categories' : collcategories, 'extra-information': extrainfo, 'authors':collauthors}
                self.accDB[collection] = collectiondata
          
        self._update_all_locked_and_completed_statuses()
        # Uncomment following for debugging
        # print self.accDB\
        
    # ======= Access functions =======
        
    def get_acc_data(self,accomID):
        return self.accDB[accomID]
        
    def get_acc_exists(self,accomID):
        return accomID in self.accDB
        
    def get_acc_title(self,accomID):
        return self.accDB[accomID]['title']
        
    def get_acc_description(self,accomID):
        return self.accDB[accomID]['description']
        
    def get_acc_needs_signing(self,accomID):
        if not 'needs-signing' in self.accDB[accomID]:
            return False
        elif (self.accDB[accomID]['needs-signing'] == "false" or self.accDB[accomID]['needs-signing'] == "False" or self.accDB[accomID]['needs-signing'] == "no"):
            return False
        else:
            return True
    
    def get_acc_depends(self,accomID):
        if 'depends' in self.accDB[accomID]:
            return [a.rstrip().lstrip() for a in self.accDB[accomID]['depends'].split(",")]
        else:
            return []
    
    def get_acc_is_unlocked(self,accomID):
        return not self.accDB[accomID]['locked']
    
    def get_trophy_path(self,accomID):
        """
        This function returns a path to the .trophy file related to given **accomplishmentID**. The trophy file may or may not exist.
        
        Args:
            * **accomID** - (str) The accomplishmentID.
            
        Returns:
            * **(str)** - A path to .trophy file of this accomplishment.
            
        Example:
            >>> acc.get_trophy_path("ubuntu-community/registered-on-launchpad")
            /home/cielak/.local/share/accomplishments/trophies/ubuntu-community/registered-on-launchpad.trophy
        """
        if not self.get_acc_exists(accomID):
            # hopefully an empty path will break something...
            return ""
        else:
            return os.path.join(self.trophies_path,accomID + ".trophy")
        
    def get_acc_is_completed(self,accomID):
        return self.accDB[accomID]['completed']
        
    def get_acc_script_path(self,accomID):
        res = self.accDB[accomID]['script-path']
        if not os.path.exists(res):
            return None
        else:
            return res
        
    def get_acc_icon(self,accomID):
        return self.accDB[accomID]['icon']
        
    def get_acc_icon_path(self,accomID):
        imagesdir = os.path.join(self.dir_cache,'trophyimages')
        imagesdir = os.path.join(imagesdir,self.get_acc_collection(accomID))
        iconfile = self.get_acc_icon(accomID)
        # XXX - this will fail if the icon passed in does not have a .
        # in the file name - LP: 1024012
        iconfilename, iconfileext = iconfile.split(".")
        if not self.get_acc_is_unlocked(accomID):
            iconfilename = iconfilename + '-locked'
        elif not self.get_acc_is_completed(accomID):
            iconfilename = iconfilename + '-opportunity'
        iconfile = iconfilename + "." + iconfileext
        return os.path.join(imagesdir,iconfile)
    
    def get_acc_needs_info(self,accomID):
        if not 'needs-information' in self.accDB[accomID]:
            return []
        return [a.rstrip().lstrip() for a in self.accDB[accomID]['needs-information'].split(",")]
    
    def get_acc_collection(self,accomID):
        """
        Returns the name of the collection this accomplishment orginates from.
        
        Args:
            * **accomID** - (str) The Accomplishment ID (e.g. 'ubuntu-community/registered-on-launchpad')
        Returns:
            * **str** - Collection name.
        Example:
            >>> acc.get_acc_collection("ubuntu-community/signed-code-of-conduct")
            ubuntu-community
        """
        return self.accDB[accomID]['collection']
        
    def get_acc_categories(self,accomID):
        """
        Returns a list of categories for a given accomplishment. This can
        include sub-categories (which are formatted like 'category:subcategory'
        (e.g. `AskUbuntu:Asking`)).

        Args:
            * **accomID** - (str) The Accomplishment ID (e.g. 'ubuntu-community/registered-on-launchpad')
        Returns:
            * **list(str)** The list of categories.
        Example:
            >>> obj.get_acc_categories("ubuntu-community/registered-on-launchpad")
            ["Launchpad"]
            >>> obj.get_acc_categories("some_other_collection/another-accomplishment")
            ["Category One", "Category Two:Subcategory"]
        """

        return self.accDB[accomID]['categories']

    def get_acc_date_completed(self,accomID):
        """
        Returns the date that the accomplishment specified by 'accomID' was
        completed.

        Args:
            accomID (str):  The Accomplishment ID (e.g. 'ubuntu-community/registered-on-launchpad')
        Returns:
            (string) The completed date
        Example:
            >>> obj.get_acc_date_completed("ubuntu-community/registered-on-launchpad")
            "2012-06-15 12:32"
        """

        return self.accDB[accomID]['date-completed']

    def get_trophy_data(self,accomID):
        """
        This function can be used to retrieve all data from a .trophy file. It returns all it's contents as a dict (provided this .trophy exists).
        
        Args:
            * **accomID** - (str) The accomplishmendID.
            
        Returns:
            - None - in case this accomplishment hasn't been completed.
            - **dict(str:str)** - in case this accomplishment has been awarded. It represents all keys and it's values in a .trophy file.
        Example:
            >>> acc.get_trophy_data("ubuntu-community/registered-on-launchpad")
            {'needs-signing': 'true', 'date-accomplished': '1990-04-12 02:22', 'needs-information': 'launchpad-email', 'version': '0.2', '__name__': 'trophy', 'launchpad-email': 'launchpaduser@ubuntu.com', 'id': 'ubuntu-community/registered-on-launchpad'}
        """
        if not self.get_acc_is_completed(accomID):
            return None
        else:
            cfg = ConfigParser.RawConfigParser()
            cfg.read(self.get_trophy_path(accomID))
            return dict(cfg._sections["trophy"])
    
    def get_collection_name(self,collection):
        """
        Returns a human-readable collection name, as it provides in it's ABOUT file.
        
        Args:
            * **collection** - (str) Sellected collection name (e.g. "ubuntu-community")
        Returns:
            * **str** - Human-readable name (e.g. "Ubuntu Comunity")
        Example:
            >>> acc.get_collection_name("ubuntu-desktop")
            Ubuntu Desktop
        """
        return self.accDB[collection]['name']
        
    def get_collection_exists(self,collection):
        """
        Checks if a collection is a valid name and is installed in the system.
        
        Args:
            * **collection** - (str) Sellected collection name (e.g. "ubuntu-community")
        Returns:
            * **bool** - Whether such collection exists or not.
        Example:
            >>> acc.get_collection_exists("ubuntu-desktop")
            True
            >>> acc.get_collection_exists("a totally wrong name")
            False
        """
        return collection in self.list_collections()
        
    def get_collection_authors(self,collection):
        """
        Returns a list of accomplishment contributors that have written accomplishments for given collection.
        
        Args:
            * **collection** - (str) Sellected collection name (e.g. "ubuntu-community")
        Returns:
            * **set(str)** - A list of accomplishment contributors names along with their e-mails (debian maintainter format).
        Example:
            >>> acc.get_collection_authors("ubuntu-community")
            set(['Surgemcgee <RobertSteckroth@gmail.com>', 'Silver Fox <silver-fox@ubuntu.com>', 'Hernando Torque <sirius@sonnenkinder.org>', 'Nathan Osman <admin@quickmediasolutions.com>', 'Rafa\xc5\x82 Cie\xc5\x9blak <rafalcieslak256@ubuntu.com>', 'Michael Hall <mhall119@ubuntu.com>', 'Angelo Compagnucci <angelo.compagnucci@gmail.com>', 'Matt Fischer <matthew.fischer@canonical.com>', 'Bruno Girin <brunogirin@gmail.com>', 'Jorge O. Castro <jorge@ubuntu.com>', 'Andrea Grandi <a.grandi@gmail.com>', 'Marco Ceppi <marco@ceppi.net>', 'Agmenor <agmenor@laposte.net>', 'Christopher Kyle Horton <christhehorton@gmail.com>', 'Jos\xc3\xa9 Antonio Rey <joseeantonior@ubuntu-pe.org>', 's.fox <silver-fox@ubuntu.com>', 'Jono Bacon <jono@ubuntu.com>'])
        """
        return self.accDB[collection]['authors']
        
    def get_collection_categories(self,collection):
        """
        Lists all categories within a given collection, as well as their subcategories.
        
        Args:
            * **collection** - (str) Sellected collection name (e.g. "ubuntu-community")
        Returns:
            * **dict(str:list(str))** - A dictionary that translates all categories into a list of their subcategories.
        Example:
            >>> acc.get_collection_categories("ubuntu-community")
            {'Development': ['Ubuntu Accomplishments', 'Packaging'],
             'QA': [],
             'Launchpad': ['Your Profile', 'Code Hosting'],
             'LoCo Teams': ['Events'],
             'Documentation': [],
             'Governance': [],
             'General': [],
             'Juju': [],
             'Ask Ubuntu': ['Membership', 'Starter Badges', 'Asking & Answering', 'Unrecognized Contributions', 'Publicity', 'Popularity', 'Starter badges', 'Chat', 'Flagging & Cleanup', 'Visiting', 'Comment', 'Tagging', 'Meta Participation', 'Voting', 'Starter', 'Editing badges'],
             'IRC': [],
             'Forums': [],
             'Events': []  }
        """
        return self.accDB[collection]['categories']
    
    def get_collection_data(self,collection):
        """
        This function returns all data stored in accDB for a given collection. It may be only useful if you need to access any data that don't have their own get_collection_* function.
        
        Args:
            * **collection** - (str) Sellected collection name (e.g. "ubuntu-community")
        Returns:
            * **dict(str:variable)** - A dictionary of all data related to this collection. List of its fields:
                * *langdefault* - (str) the default language of this collection, as specified in it's ABOUT file
                * *acc_num* - (int) the number of accomplishments in this collection
                * *base_path* - (str) the path where this collection is installed
                * *type* - (str) always equal to "collection"
                * *name* - (str) human-readable name, use get_collection_name instead
                * *authors* - set(str) list of authors, use get_collection_authors instead
                * *extra-information* - dict(str:dict(str:str)) list of all extra-information used with it's medatada, use get_extra_information or get_all_extra_information instead
                * *categories* - dict(str:list(str)) list of all categories and subcategories, use get_collection_categories instead
        """
        return self.accDB[collection]
        
    # ====== Listing functions ======
    
    def list_accomplishments(self):
        return [acc for acc in self.accomslist()]
        
    def list_trophies(self):
        return [acc for acc in self.accomslist() if self.get_acc_is_completed(acc)]
        
    def list_opportunitues(self):
        return [acc for acc in self.accomslist() if not self.get_acc_is_completed(acc)]
        
    def list_depending_on(self,accomID):
        return [acc for acc in self.accomslist() if accomID in self.get_acc_depends(acc)]
        
    def list_unlocked(self):
        return [acc for acc in self.accomslist() if self.get_acc_is_unlocked(acc)]
        
    def list_unlocked_not_completed(self):
        return [acc for acc in self.accomslist() if self.get_acc_is_unlocked(acc) and not self.get_acc_is_completed(acc)]        
    
    def list_collections(self):
        return [col for col in self.accDB if self.accDB[col]['type'] == 'collection']

    # ====== Scriptrunner functions ======

    def run_script(self,accomID):
        if not self.get_acc_exists(accomID):
            return
        self.run_scripts([accomID])

    def run_scripts(self, which=None):
        if isinstance(which, list):
            to_schedule = which
        elif which == None:
            to_schedule = self.list_unlocked_not_completed()
        else:
            log.msg("Note: This call to run_scripts is incorrect, run_scripts takes (optionally) a list of accomID to run their scripts")
            to_schedule = self.list_unlocked_not_completed()

        if len(to_schedule) == 0:
            log.msg("No scripts to run, returning without starting "\
                "scriptrunner")
            return

        log.msg("Adding to scripts queue: %s " % (str(to_schedule)))
        for i in to_schedule:
            if not i in self.scripts_queue:
                self.scripts_queue.append(i)
        self.asyncapi.start_scriptrunner()

    # ====== Viewer-specific functions ======

    def build_viewer_database(self):
        accs = self.list_accomplishments()
        db = []
        for acc in accs:
            db.append({ 
                'title' :           self.get_acc_title(acc),
                'accomplished' :    self.get_acc_is_completed(acc),
                'locked' :      not self.get_acc_is_unlocked(acc),
                'date-completed' :      self.get_acc_date_completed(acc),
                'iconpath' :        self.get_acc_icon_path(acc),
                'collection' :      self.get_acc_collection(acc),
                'collection-human' :self.get_collection_name(
                                        self.get_acc_collection(acc) ),
                'categories' :      self.get_acc_categories(acc),
                'id' :              acc 
                })
        return db
        
    # ========= Misc functions ===========
    
    def get_published_status(self):
        """Detect if we are currently publishing online or not. Returns
        True if we are or False if we are not. """

        trophydir = self.get_config_value("config", "trophypath")
        print trophydir
        if os.path.exists(os.path.join(trophydir, "WEBVIEW")):
            return True
        else:
            return False

    def accomplish(self,accomID):
        log.msg("Accomplishing: %s" % accomID)
        if not self.get_acc_exists(accomID):
            log.msg("There is no such accomplishment.")
            return False #failure

        # Check if is hasn't been already completed
        if self.get_acc_is_completed(accomID):
            log.msg("Not accomplishing " + accomID + ", it has already been completed.")
            return True #success

        # Check if this accomplishment is unlocked
        if not self.get_acc_is_unlocked(accomID):
            log.msg("This accomplishment cannot be completed; it's locked.")
            return False

        coll = self._coll_from_accomID(accomID)
        accdata = self.get_acc_data(accomID)

        # Prepare extra-info
        needsinformation = self.get_acc_needs_info(accomID)
        for i in needsinformation:
            accdata[i] = self.get_extra_information(coll,i)[0][i]

        # Create .trophy file
        self._create_trophy_file(accdata, accomID)

        if not self.get_acc_needs_signing(accomID):
            # The accomplishment does not need signing!
            if not self.test_mode:
                self.service.trophy_received(accomID)
            self._display_accomplished_bubble(accomID)
            self._display_unlocked_bubble(accomID)
            # Mark as completed and get list of new opportunities
            just_unlocked = self._mark_as_completed(accomID)
            self.run_scripts(just_unlocked)

        return True

    def _create_trophy_file(self, accdata, accomID):
        # Create .trophy file
        cp = ConfigParser.RawConfigParser()
        cp.add_section("trophy")
        cp.set("trophy", "version", "0.2")
        cp.set("trophy", "id", accomID)
        now = datetime.datetime.now()
        cp.set("trophy", "date-accomplished", now.strftime("%Y-%m-%d %H:%M"))
        if 'needs-signing' in accdata:
            cp.set("trophy", 'needs-signing', accdata['needs-signing'])
        if 'needs-information' in accdata:
            cp.set("trophy", 'needs-information', accdata['needs-information'])
            for i in accdata['needs-information'].split(","):
                a = i.rstrip().lstrip()
                cp.set("trophy", a, accdata[a])
        trophypath = self.get_trophy_path(accomID)
        dirpath = os.path.split(trophypath)[0]
        if not os.path.exists(dirpath):
            os.makedirs(dirpath)
        log.msg(trophypath)
        fp = open(trophypath, "w")
        cp.write(fp)
        fp.close()

    def set_daemon_session_start(self,value):
        log.msg(value)
        log.msg(type(value))
        if value == True:
            log.msg("setting")
            command = "twistd -noy " + daemon_exec_dir + "/accomplishments-daemon --logfile=" + os.path.join(self.dir_cache, "logs", "daemon.log")
            filetext = "[Desktop Entry]\n\
Type=Application\n\
Encoding=UTF-8\n\
Name=Accomplishments Daemon\n\
Exec=" + command + "\n\
NoDisplay=true"
            filename = os.path.join(self.dir_autostart, "accomplishments-daemon.desktop")
            file = open(filename, "w")
            file.write(filetext)
            file.close
            self.write_config_file_item("config", "daemon_sessionstart", "true")
        elif value == False:
            filename = os.path.join(self.dir_autostart, "accomplishments-daemon.desktop")
            if os.path.exists(filename):
                os.remove(filename)
            self.write_config_file_item("config", "daemon_sessionstart", "false")
            
    def get_daemon_session_start(self):
        return self.get_config_value("config", "daemon_sessionstart")
    
    def set_block_ubuntuone_notification_bubbles(self,value):
        u1configdir = os.path.join(
            xdg.BaseDirectory.xdg_config_home, "ubuntuone")

        if not os.path.exists(u1configdir):
            os.makedirs(u1configdir)

        cfile = os.path.join(u1configdir, "syncdaemon.conf")

        config = ConfigParser.ConfigParser()
        config.read(cfile)
        
        if value == True:
            if not config.has_section("notifications"):
                config.add_section('notifications')
            config.set('notifications', 'show_all_notifications', "False")
        elif value == False:
            if config.has_section("notifications"):
                config.set('notifications', 'show_all_notifications', "True")
        
        with open(cfile, 'wb') as configfile:
            config.write(configfile)
            
    def get_block_ubuntuone_notification_bubbles(self):
        u1configdir = os.path.join(
            xdg.BaseDirectory.xdg_config_home, "ubuntuone")

        cfile = os.path.join(u1configdir, "syncdaemon.conf")
        if os.path.exists(cfile):

            config = ConfigParser.ConfigParser()
            config.read(cfile)

            if(config.read(cfile)):
                if config.has_section("notifications"):
                    val = config.get('notifications', 'show_all_notifications')
                    if val == "false" or val == "False":
                        return True
                    else:
                        return False
        else:
            return False

    def _coll_from_accomID(self,accomID):
        return accomID.split("/")[0]

    def _display_accomplished_bubble(self,accomID):
        if self.show_notifications == True and pynotify and (
            pynotify.is_initted() or pynotify.init("icon-summary-body")):
            n = pynotify.Notification(
                _("You have accomplished something!"),
                self.get_acc_title(accomID),
                self.get_acc_icon_path(accomID) )
            n.set_hint_string('append', 'allowed')
            n.show()

    def _display_unlocked_bubble(self,accomID):
        unlocked = len(self.list_depending_on(accomID))
        if unlocked is not 0:
            if self.show_notifications == True and pynotify and (
                pynotify.is_initted() or pynotify.init("icon-summary-body")):
                message = (N_("You have unlocked %s new opportunity.","You have unlocked %s new opportunities.",unlocked) % str(unlocked))
                n = pynotify.Notification(
                    _("Opportunities Unlocked!"), message,
                    self.get_media_file("unlocked.png"))
                n.show()
    
    def accomslist(self):
        for k in self.accDB:
            if self.accDB[k]['type'] is "accomplishment":
                yield k
            
    def _get_is_asc_correct(self,filepath):
        if os.path.exists(filepath):
            # the .asc signed file exists, so let's verify that it is correctly
            # signed by the Matrix
            trophysigned = open(filepath, "r")
            trophy = open(filepath[:-4], "r")
            c = gpgme.Context()

            signed = StringIO(trophysigned.read())
            plaintext = StringIO(trophy.read())
            sig = c.verify(signed, None, plaintext)

            if len(sig) != 1:
                # No Sig
                return False

            if sig[0].status is not None:
                # Bad Sig
                return False
            else:
                # Correct!
                # result = {'timestamp': sig[0].timestamp, 'signer': sig[0].fpr}
                return True
        else:
            log.msg("Cannot check if signature is correct, because file %s does not exist" % filepath)
            return False
            
    def _check_if_acc_is_completed(self,accomID):
        trophypath = self.get_trophy_path(accomID)
        if not os.path.exists(trophypath):
            # There is no trophy file
            return False
        if not self.get_acc_needs_signing(accomID):
            # The trophy does not need a signature
            return True
        else:
            # The trophy needs to be signed
            ascpath = trophypath + ".asc"
            if not os.path.exists(ascpath):
                return False
            else:
                return self._get_is_asc_correct(ascpath)
        
    def _check_if_acc_is_locked(self,accomID):
        dep = self.get_acc_depends(accomID)
        if not dep:
            return False
        else:
            locked = False
            for d in dep:
                # If at least one dependency is not completed...
                if not self.get_acc_is_completed(d):
                    locked = True
                    break
            return locked
            
    def _update_all_locked_and_completed_statuses(self):
        accs = self.list_accomplishments()
        for acc in accs:
            self.accDB[acc]['completed'] = self._check_if_acc_is_completed(acc)
            if self.accDB[acc]['completed'] == True:
                self.accDB[acc]['date-completed'] = self._get_trophy_date_completed(acc)
            else:
                self.accDB[acc]['date-completed'] = "None"
        for acc in accs:
            self.accDB[acc]['locked'] = self._check_if_acc_is_locked(acc)
         
    def _get_trophy_date_completed(self, accomID):
        trophypath = self.get_trophy_path(accomID)
        if not os.path.exists(trophypath):
            # There is no trophy file
            return False

        config = ConfigParser.RawConfigParser()
        cfile = trophypath
        config.read(cfile)

        if config.has_option("trophy", "date-accomplished"):
            return config.get("trophy", "date-accomplished")

    def _mark_as_completed(self,accomID):
        # Marks accomplishments as completed int the accDB, and returns a list
        # of accomIDs that just got unlocked.
        self.accDB[accomID]['completed'] = True
        self.accDB[accomID]['date-completed'] = self._get_trophy_date_completed(accomID)
        accs = self.list_depending_on(accomID)
        res = []
        for acc in accs:
            before = self.accDB[acc]['locked']
            self.accDB[acc]['locked'] = self._check_if_acc_is_locked(acc)
            # If it just got unlocked...
            if (before == True and self.accDB[acc]['locked'] == False):
                res.append(acc)
        return res
            
    #Other significant system functions
    def get_API_version(self):
        return "0.2"
