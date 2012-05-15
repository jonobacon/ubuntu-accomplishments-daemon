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
from ubuntuone.couch import auth

import accomplishments
from accomplishments import exceptions
from accomplishments.daemon import dbusapi
from accomplishments.util import get_data_file, SubprocessReturnCodeProtocol
from accomplishments.util.paths import media_dir, module_dir1, module_dir2, installed, locale_dir

gettext.bindtextdomain('accomplishments-daemon',locale_dir)
gettext.textdomain('accomplishments-daemon')

os.environ["PYTHONPATH"] = "$PYTHONPATH:."
# The directories with accomplishment.* modules, that are being used by scripts,
# may happen to be in a completelly different directory, if the daemon was
# installed using a non-default prefix.
if installed:
    os.environ["PYTHONPATH"] = module_dir1 + ":" + module_dir2 + ":" + os.environ["PYTHONPATH"]

MATRIX_USERNAME = "openiduser155707"
LOCAL_USERNAME = getpass.getuser()
SCRIPT_DELAY = 900

#flags used for scripts_state
NOT_RUNNING = 0
RUNNING = 1
NEEDS_RE_RUNNING = 2

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

    @staticmethod
    def run_a_subprocess(command):
        log.msg("Running subprocess command: " + str(command))
        pprotocol = SubprocessReturnCodeProtocol()
        reactor.spawnProcess(pprotocol, command[0], command, env=os.environ)
        return pprotocol.returnCodeDeferred

    # XXX let's rewrite this to use deferreds explicitly
    @defer.inlineCallbacks
    def wait_until_a_sig_file_arrives(self):
        path, info = yield self.parent.sd.wait_for_signals(
            signal_ok="DownloadFinished",
            success_filter=lambda path,
            info: path.startswith(self.parent.trophies_path)
            and path.endswith(".asc"))
        log.msg("Trophy signature recieved...")
        time.sleep(2)
        accomname = os.path.splitext(os.path.splitext(
            os.path.split(path)[1])[0])[0]
        
        valid = self.parent.validate_trophy(path)
        if not valid:
            log.msg("WARNING: invalid .asc signature recieved from the server!")
        
        if valid == True:
            item = os.path.split(path)[1][:-11]
            app = os.path.split(os.path.split(path)[0])[1]
            accomID = app + "/" + item
            data = self.parent.get_accomplishment_information(item)
            iconpath = os.path.join(
                self.parent.accomplishments_path,
                data[0]["application"],
                "trophyimages",
                data[0]["icon"])

            self.parent.service.trophy_received(accomID)
            if self.parent.show_notifications == True and pynotify and (
            pynotify.is_initted() or pynotify.init("icon-summary-body")):
                trophy_icon_path = "file://%s" % os.path.realpath(
                    os.path.join(
                        os.path.split(__file__)[0],
                        "trophy-accomplished.svg"))
                n = pynotify.Notification(
                    _("You have accomplished something!"), data[0]["title"], iconpath)
                n.show()

            # check to see if there are any unlocked accomplishments
            self.parent.show_unlocked_accomplishments(accomID)
            
        self.parent.run_scripts(0)
        self.wait_until_a_sig_file_arrives()

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
                trophydir, MATRIX_USERNAME, LOCAL_USERNAME + " Trophies Folder"
                + " (" + timeid + ")", "Modify")
            log.msg(
                "...share has been offered (" + trophydir + "" + ", "
                + MATRIX_USERNAME + ", " + LOCAL_USERNAME + ")")
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
                trophydir, MATRIX_USERNAME, LOCAL_USERNAME + " Trophies Folder"
                + " (" + timeid + ")", "Modify")
            log.msg("...share has been offered (" + trophydir + "" + ", "
                + MATRIX_USERNAME + ", " + LOCAL_USERNAME + ")")
            log.msg("...offered the share.")
            return
        else:
            log.msg("The folder is shared, with: %s" % ", ".join(
                shared_to))
            return

    # XXX let's rewrite this to use deferreds explicitly
    @defer.inlineCallbacks
    def run_scripts_for_user(self, uid):
        # The following avoids running multiple instances of this function,
        # which might get very messy and cause a lot of trouble. Simulatnously
        # run scripts would be the case if user recieves several .asc files
        # within a short time, the scripts take extraordinary time to run,
        # or for various other reasons.
        # NOTE: detailed explanation of scripts_state mechanism is included
        # near it's initialisation in Accomplishments.__init__(...).
        if uid in self.parent.scripts_state:
            if self.parent.scripts_state[uid] is RUNNING:
                log.msg("Aborting running scripts, execution already in progress. Will re-do this when current run ends.")
                # scripts are already being run for that user, but since something
                # called that function, maybe we need to re-run them because
                # something has changed since last call, so let's schedule the
                # re-running immidiatelly after finishing this run, and abort
                self.parent.scripts_state[uid] = NEEDS_RE_RUNNING
                return
            elif self.parent.scripts_state[uid] is NEEDS_RE_RUNNING:
                log.msg("Aborting running scripts, execution already in progress. Re-runing scripts has already been scheduled.")
                # already scheduled, so just aborting
                return
        # if above conditions failed, that means the scripts are not being run
        # this user, so we can continue normally, marking the scripts as running...
        self.parent.scripts_state[uid] = RUNNING
            
        log.msg("--- Starting Running Scripts ---")
        timestart = time.time()
        self.parent.service.scriptrunner_start()

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
            self.parent.scripts_state[uid] = NOT_RUNNING #unmarking to avoid dead-lock
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
            self.parent.scripts_state[uid] = NOT_RUNNING #unmarking to avoid dead-lock
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
        accoms = self.parent.get_all_available_accomplishments_with_scripts()
                
        totalscripts = len(accoms)
        log.msg("Need to run (%d) scripts" % totalscripts)

        scriptcount = 1
        for accom in accoms:
            msg = "%s/%s: %s" % (scriptcount, totalscripts, accom["_script"])
            log.msg(msg)
            exitcode = yield self.run_a_subprocess([accom["_script"]])
            if exitcode == 0:
                self.parent.accomplish(
                    accom["application"] + "/" + accom["accomplishment"])
                log.msg("...Accomplished")
            elif exitcode == 1:
                log.msg("...Not Accomplished")
            elif exitcode == 2:
                log.msg("....Error")
            elif exitcode == 4:
                log.msg("...Could not get launchpad email")
            else:
                log.msg("...Error code %d" % exitcode)
            scriptcount = scriptcount + 1

        os.environ = oldenviron

        # XXX eventually the code in this method will be rewritten using
        # deferreds; as such, we're going to have to be more clever regarding
        # timing things...
        timeend = time.time()
        timefinal = round((timeend - timestart), 2)

        log.msg(
            "--- Completed Running Scripts in %.2f seconds---" % timefinal)
        self.parent.service.scriptrunner_finish()
        
        # checking whether this function was called while script execution was in progress...
        rerun = (self.parent.scripts_state[uid] is NEEDS_RE_RUNNING)
        # unsetting the lock
        self.parent.scripts_state[uid] = NOT_RUNNING
        # re-running scripts if needed
        if rerun:
            log.msg("Re-running scripts as intended...")
            self.run_scripts_for_user(uid)


class Accomplishments(object):
    """The main accomplishments daemon.

    No D-Bus required, so that it can be used for testing.
    """
    def __init__(self, service, show_notifications=None):
        self.accomplishments_installpaths = None
        self.trophies_path = None
        self.has_u1 = None
        self.has_verif = None
        
        self.lang = locale.getdefaultlocale()[0]
        
        # use this to override the language for testing
        #self.lang = "pt_BR"
        self.accomlangs = []
        self.service = service
        self.dir_config = None
        self.dir_data = None
        self.dir_cache = None
        self.depends = []
        self.processing_unlocked = False
        self.asyncapi = AsyncAPI(self)

        # The following dictionary represents state of scripts.
        # It's a dictionary and not a single variable, because scripts may be run
        # for each user independently. For each user, the state can be either
        # RUNNING, NOT_RUNNING or NEEDS_RE_RUNNING. If an entry for a
        # particular UID does not exist, it should be treated as NOT_RUNNING.
        # The use of this flag is to aviod running several instances of 
        # run_scripts_for_user, which might result in undefined, troubleful
        # behavior. The flags are NOT_RUNNING by default, and are set to
        # RUNNING when the run_scripts_for_user starts. However, if it has been
        # already set to RUNNING, the function will abort, and will instead set the
        # flag to NEEDS_RE_RUNNING, in order to mark that the scripts have to
        # be run once more, because something might have changed since we run
        # them the last time (as the run_scripts_for_user was called while 
        # scripts were being executed). Setting the flag to NEEDS_RE_RUNNING 
        # will cause run_scripts_for_user to redo everything after having
        # finished it's current task in progress. Otherwise it will eventually
        # set the flag back to NOT_RUNNING.
        self.scripts_state = {}

        # create config / data dirs if they don't exist
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

        print str("------------------- Ubuntu Accomplishments Daemon Log"
            "- "+ str(datetime.datetime.now()) +" -------------------")

        self._load_config_file()

        print str("Accomplishments install paths: " + self.accomplishments_installpaths)
        print str("Trophies path: " + self.trophies_path)

        self.show_notifications = show_notifications
        log.msg("Connecting to Ubuntu One")
        self.sd = SyncDaemonTool()

        self.reload_accom_database()
        print self.list_unlocked_not_completed()
        print self.get_acc_data("ubuntu-community/infrastructure/registered-on-launchpad")
		
        # XXX this wait-until thing should go away; it should be replaced by a
        # deferred-returning function that has a callback which fires off
        # generate_all_trophis and schedule_run_scripts...
        self.asyncapi.wait_until_a_sig_file_arrives()
        self._create_all_trophy_icons()

    def get_media_file(self, media_file_name):
        log.msg("MEDIA_FILE_NAME:")
        log.msg(media_file_name)
        log.msg("MEDIA_DIR:")
        log.msg(media_dir)
        #media_filename = get_data_file(media_dir.split, '%s' % (media_file_name,))
        media_filename = os.path.join(media_dir, media_file_name)
        log.msg("MEDIA_FILENAME:")
        log.msg(media_filename)

        if not os.path.exists(media_filename):
            media_filename = None

        final = "file:///" + media_filename
        return final

    def show_unlocked_accomplishments(self, accomID):
        """
        Determine if accomplishments have been unlocked and display a
        notify-osd bubble.
        """

        files = self.get_accom_dependencies(accomID)
        unlocked = len(files)

        if unlocked is not 0:
            if self.show_notifications == True and pynotify and (
            pynotify.is_initted() or pynotify.init("icon-summary-body")):
                message = (N_("You have unlocked %s new opportunity.","You have unlocked %s new opportunities.",unlocked) % str(unlocked))
                n = pynotify.Notification(
                    _("Opportunities Unlocked!"), message,
                    self.get_media_file("unlocked.png"))
                n.show()

        self.depends = []

    def _get_trophies_files_list(self):
        """Return a list of all trophy files. Please note: these are
        raw .trophy files and for machine-verifiable accomplishments
        some of these files may have not been verified."""
        
        log.msg("Looking for trophies files in "
                     + self.trophies_path)
        trphy_files = os.path.join(self.trophies_path,
            "*", "*.trophy")
        return glob.glob(trphy_files)

    def _load_accomplishment_file(self, f):
        log.msg("Loading accomplishments file: " + f)
        config = ConfigParser.RawConfigParser()
        config.read(f)
        data = dict(config._sections["accomplishment"])
        data["_filename"] = f
        data["accomplishment"] = os.path.splitext(os.path.split(f)[1])[0]
        data["accomplishment"] = os.path.splitext(os.path.split(f)[1])[0]
        return data


    def _load_trophy_file(self, f):
        log.msg("Load trophy file: " + f)
        config = ConfigParser.RawConfigParser()
        config.read(f)
        data = dict(config._sections["trophy"])
        data["_filename"] = f
        data["accomplishment"] = os.path.splitext(os.path.split(f)[1])[0]
        return data

    def get_all_accomplishments(self):
        log.msg("List all accomplishments")
        log.msg(files)
        fs = [self._load_accomplishment_file(f) for f in
            self._get_accomplishments_files_list()]
        return fs

    def _create_all_trophy_icons(self):
        """Iterate through each of the accomplishments on the system
        and generate all of the required icons that we provide to
        clients."""
        
        paths = []
        final = []
        files = self._get_accomplishments_files_list()

        for f in files:
            paths.append(os.path.split(f)[0])

        paths = list(set(paths))

        for p in paths:
            app = os.path.split(os.path.split(p)[0])[1]
            app_trophyimagespath = os.path.join(os.path.split(p)[0], "trophyimages")
            cache_trophyimagespath = os.path.join(
                self.dir_cache, "trophyimages", app)
            if not os.path.exists(cache_trophyimagespath):
                os.makedirs(cache_trophyimagespath)

            # first delete existing images
            lockedlist=glob.glob(cache_trophyimagespath + "/*locked*")

            opplist=glob.glob(cache_trophyimagespath + "/*opportunity*")

            for l in lockedlist:
                os.remove(l)

            for o in opplist:
                os.remove(o)

            # now generate our trophy images
            lock_image_path = os.path.join(media_dir, "lock.png")
            self._create_trophy_icons(
                app_trophyimagespath, cache_trophyimagespath, lock_image_path)

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

    def _create_trophy_icons(self, infolder, outfolder, watermark):
        """Generate a set of trophy icons for a given accomplishment
        set."""
        mark = Image.open(watermark)
        for root, dirs, files in os.walk(infolder):
            for name in files:
                try:
                    im = Image.open(os.path.join(root, name))
                    filename = os.path.join(outfolder, name)
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

    def get_accom_dependencies(self, accomID):
        """Return a list of all the dependencies for a given accomplishment.
        This is returned as a list. An empty set will return an empty list."""

        files = self._get_accomplishments_files_list()
                
        depterm = accomID
        results = []
        
        for f in files:
            config = ConfigParser.ConfigParser()
            config.read(f)

            if config.has_option("accomplishment", "depends"):
                item = config.get("accomplishment", "depends")
                if item == depterm:
                    results.append(f)

        return results

    def verify_ubuntu_one_account(self):
        # check if this machine has an Ubuntu One account
        log.msg("Check if this machine has an Ubuntu One account...")
        u1auth_response = auth.request(
            url='https://one.ubuntu.com/api/account/')
        u1email = None
        if not isinstance(u1auth_response, basestring):
            u1email = json.loads(u1auth_response[1])['email']
        else:
            log.msg("No Ubuntu One account is configured.")

        if u1email is None:
            log.msg("...No.")
            log.msg(u1auth_response)
            self.has_u1 = False
            return False
        else:
            log.msg("...Yes.")
            self.has_u1 = True
            return True

    def get_config_value(self, section, item):
        """Return a configuration value from the .accomplishments file"""
        log.msg(
            "Returning configuration values for: %s, %s", section, item)
        homedir = os.getenv("HOME")
        config = ConfigParser.RawConfigParser()
        cfile = self.dir_config + "/.accomplishments"
        config.read(cfile)

        if section == "config" and item == "has_u1":
            item = config.getboolean(section, item)
            return item
        elif section == "config" and item == "has_verif":
            item = config.getboolean(section, item)
            return item
        else:
            item = config.get(section, item)
            return item

    def write_config_file_item(self, section, item, value):
        """Set a configuration value in the .accomplishments file"""
        log.msg(
            "Set configuration file value in '%s': %s = %s", section, item,
            value)
        homedir = os.getenv("HOME")
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
        homedir = os.getenv("HOME")
        config = ConfigParser.RawConfigParser()
        cfile = self.dir_config + "/.accomplishments"

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
        
        homedir = os.environ["HOME"]
        config = ConfigParser.RawConfigParser()
        cfile = os.path.join(self.dir_config, ".accomplishments")

        u1ver = self.verify_ubuntu_one_account()

        if u1ver is False:
            self.has_u1 = False
        else:
            self.has_u1 = True

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
        else:
            # setting accomplishments path to the system default
            accompath = "/usr/share/accomplishments"
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

    def get_all_extra_information(self):
        """
        Return a dictionary of all information for the accomplishments
        to authticate. Returns {application, needs-information, label,
        description, value}.
        """
        # get a list of all accomplishment files
        accomplishments_files = self._get_accomplishments_files_list()
        
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
        for f in accomplishments_files:
            # get the path to the directory of accomplishments set's
            # "extrainformation" dir - it is useful, because it contains
            # translated labels and descriptions
            accomextrainfo = os.path.join(
                os.path.split(f)[0], "../extrainformation")
                
            # a temporary variable, representing a single entry of the list this function returns
            d = {}
            
            # prepare a ConfigParser, that will read the .accomplishment file
            accomconfig = ConfigParser.RawConfigParser()
            accomconfig.read(f)
            
            # proceed only if the accomplishment file has 'needs-information'
            # key [in other case we can skip it, as it does not require any ExtraInformation]
            config_args = ("accomplishment", "needs-information")
            if accomconfig.has_option(*config_args) == True:
            
                # prepare the path to accomplishment set's extrainformation file
                # [e.g. [...]accomplishments/ubuntu-community/extrainformation/launchpad-email]
                infofile = os.path.join(accomextrainfo, accomconfig.get(*config_args))
                
                # and then read that file with a config parser
                infoconfig = ConfigParser.RawConfigParser()
                infoconfig.read(infofile)
                
                # we need the set's ABOUT file, to determine the default language.
                # let's read it with a config parser too
                aboutset_path = os.path.join(os.path.split(f)[0], "../ABOUT")
                aboutconfig = ConfigParser.RawConfigParser()
                aboutconfig.read(aboutset_path)
                
                # this will store the set's default language in deflang
                deflang = aboutconfig.get("general","langdefault")
                
                # if the item's label in user's language is present, get it;
                # otherwise get the label in default language
                
                if infoconfig.has_option("label", self.lang):
                    label = infoconfig.get("label", self.lang)
                elif infoconfig.has_option("label", deflang):
                    label = infoconfig.get("label", deflang)
                else:
                    label = infoconfig.get("label", "en")
                    
                # similarly, get the item's description, use default language
                # in case it's not translated to user's language
                if infoconfig.has_option("description",self.lang):
                    desc = infoconfig.get("description", self.lang)
                elif infoconfig.has_option("description", deflang):
                    desc = infoconfig.get("description", deflang)
                else:
                    desc = infoconfig.get("description", "en")
                    
                # we also need to know whether user has already set this item's value.
                # to do this, simply check whether trophies/.extrainformation/<item> file exists.
                try:
                    valuefile = open(trophyextrainfo + str(accomconfig.get(*config_args)))
                    # if we got here without an exception, it means that the file exists
                    # so, we can read it's value
                    value = valuefile.readline()
                    value = value.rstrip() # get rid of the tailing newline
                    # and build up the dictionary of all data for a single ExtraInformation field
                    d = {
                        "application" : accomconfig.get("accomplishment", "application"),
                        "needs-information" : accomconfig.get(*config_args),
                        "label" : label,
                        "description" : desc,
                        "value" : value}
                except IOError as e:
                    # we got an exception, so it seems that the file is not present - we'll use "" as the value, to indicate that it's empty
                    d = {
                        "application" : accomconfig.get("accomplishment", "application"),
                        "needs-information" : accomconfig.get(*config_args),
                        "label" : label,
                        "description" : desc,
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
        Return a dictionary of all information required for the accomplishments
        to authticate that has not been set yet. Returns {application,
        needs-information, label, description} Returns only these, which value is not set.
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

    def get_all_accomplishments_and_status(self):
        """
        Provide a list of all accomplishments and whether they have been
        accomplished or not, including validating the trophies. Returns a list
        of dictionaries.
        """
        if self.depends == []:
            getdepends = True
        else:
            getdepends = False

        log.msg("List all accomplishments and status")
        accomplishments_files = self._get_accomplishments_files_list()
        things = {}
        for accomplishment_file in accomplishments_files:
            path, name = os.path.split(accomplishment_file)
            name = os.path.splitext(name)[0]
            lang = os.path.split(path)[1]
            app = os.path.split(os.path.split(path)[0])[1]
            data = self._load_accomplishment_file(accomplishment_file)

            icon = data["icon"]
            #icondir = os.path.join(os.path.split(
            #   accomplishment_file)[0], "trophyimages")
            icondir = os.path.join(
                self.dir_cache, "trophyimages", data["application"])
            iconname = os.path.splitext(icon)[0]
            iconext = os.path.splitext(icon)[1]

            # find the human readable name of the application and add it to the
            # dict
            
            #BROKEN:
            #accompath = os.path.join(
            #    self.accomplishments_path, data["application"])
            infofile = os.path.join(accompath, "ABOUT")
            config = ConfigParser.RawConfigParser()
            config.read(infofile)
            final = config.get("general", "name")

            data["application-human"] = final

            # If the trophy file exists, this must be accomplished and not
            # locked
            trophy_file = os.path.join(
                self.trophies_path, app, "%s.trophy" % name)
                
            trophysigned = str(trophy_file) + ".asc"
            
            acc_file_cfg = ConfigParser.RawConfigParser()
            acc_file_cfg.read(accomplishment_file)
            acc_data = dict(acc_file_cfg._sections["accomplishment"])
            if(acc_data.has_key("needs-signing") and (acc_data["needs-signing"] == True or acc_data["needs-signing"] == "True" or acc_data["needs-signing"] == "true")):
                # this trophy needs to be signed in order to be validated
                valid = self.validate_trophy(trophysigned)
            else:
                # this trophy does not require signature
                valid = os.path.exists(trophy_file)


            if valid:
                data["accomplished"] = True
                data["locked"] = False
                data.update(self._load_trophy_file(trophy_file))
                data["iconpath"] = os.path.join(icondir, icon)
            else:
                if os.path.exists(trophysigned):
                    os.remove(trophysigned)
                    # os.remove(trophy_file)
                data["accomplished"] = False
                data["iconpath"] = os.path.join(icondir, (
                    iconname + "-opportunity" + iconext))
                # can't tell if it's locked until we've seen all trophies
            things[accomplishment_file] = data
        # Now go through the list again and check if things are locked
        for accomplishment_file in things:
            accomlang = os.path.split(
                os.path.split(accomplishment_file)[0])[1]
            item = things[accomplishment_file]
            if item["accomplished"] == False:
                locked = False
                depends_list = item.get("depends")
                if depends_list:
                    dependencies = depends_list.split(",")
                    for dependency in dependencies:
                        dapp, dname = dependency.split("/")

                        # we need to check the language of the dependency
                        # as it may be in a different set and be a different
                        # language.
                        for l in self.accomlangs:
                            if dapp in l:
                                dapplang = l[dapp]

                        #BROKEN:
                        #daccomplishment_file = os.path.join(
                        #    self.accomplishments_path, dapp, dapplang,
                        #    "%s.accomplishment" % dname)
                        daccomplishment_data = things[daccomplishment_file]
                        if daccomplishment_data["accomplished"] == False:
                            # update the list of dependencies
                            if getdepends == True:
                                depends_key = str(
                                    item["application"]) + "/" + str(
                                        item["accomplishment"])
                                self.depends.append(
                                    {depends_key: depends_list})
                            locked = True
                            itemicon = item["icon"]
                            itemiconname = os.path.splitext(itemicon)[0]
                            itemiconext = os.path.splitext(itemicon)[1]
                            item["iconpath"] = os.path.join(
                                os.path.split(item["iconpath"])[0],
                                (itemiconname + "-locked" + itemiconext))
                item["locked"] = locked
                #item["icon"] = os.path.join(
                #   icondir, (iconname + "-opportunity" + iconext))
        return things.values()

    def get_all_available_accomplishments_with_scripts(self):
        log.msg("List all accomplishments with scripts")
        available = [accom for accom in self.get_all_accomplishments_and_status()
            if not accom["accomplished"] and not accom["locked"]]
        withscripts = []
        for accom in available:
            path, name = os.path.split(accom["_filename"])
            name = os.path.splitext(name)[0]
            lang = os.path.split(path)[1]
            app = os.path.split(os.path.split(path)[0])[1]
            #path, name = os.path.split(accom["_filename"])
            #name = os.path.splitext(name)[0]
            #app = os.path.split(path)[1]
            scriptglob = glob.glob(os.path.join(
                self.scripts_path, app, "%s.*" % name))
            if scriptglob:
                accom["_script"] = scriptglob[0]
                withscripts.append(accom)
        return withscripts

    def get_accomplishment_information(self, accomplishment):
        """Returns information for the given accomplishment."""
        
        log.msg("Getting accomplishment info for " + accomplishment)
        search = "/" + accomplishment + ".accomplishment"
        files = self._get_accomplishments_files_list()
        match = None

        data = []

        for i in files:
            if search in i:
                match = i

        config = ConfigParser.RawConfigParser()
        config.read(match)
        data.append(dict(config._sections["accomplishment"]))
        return data

    def get_trophy_information(self, trophy):
        log.msg("Getting trophy info for " + trophy)
        search = "/" + trophy + ".trophy"
        files = self._get_trophies_files_list()
        match = None

        data = []

        for i in files:
            if search in i:
                match = i

        config = ConfigParser.RawConfigParser()
        config.read(match)
        data.append(dict(config._sections["trophy"]))
        return data

    def run_scripts_for_all_active_users(self):
        for uid in [x.pw_uid for x in pwd.getpwall()
            if x.pw_dir.startswith('/home/') and x.pw_shell != '/bin/false']:
            os.seteuid(0)
            self.asyncapi.run_scripts_for_user(uid)

    def run_scripts(self, run_by_client):
        uid = os.getuid()
        if uid == 0:
            log.msg("Run scripts for all active users")
            self.run_scripts_for_all_active_users()
        else:
            log.msg("Run scripts for user")
            self.asyncapi.run_scripts_for_user(uid)

    def create_extra_information_file(self, item, data):
        """Does exactly the same as write_extra_information_file(), but it does not
           overwrite any existing data"""
           
        # XXX this should be removed as we are using write_extra_information_file
        log.msg(
            "Creating Extra Information file: %s, %s", item, data)
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
            
    def write_extra_information_file(self, item, data):

        log.msg(
            "Saving Extra Information file: %s, %s", item, data)
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
        """Removes all trophies that use this extra-info. This is useful
        for re-authorizing trophies when extra-information changes."""
        trophylist = self._get_trophies_files_list()
        for trophyfile in trophylist:
            config = ConfigParser.RawConfigParser()
            config.read(trophyfile)
            if config.has_option("trophy","needs-information"):
                needs = config.get("trophy","needs-information")
                if extrainfo in needs:
                    #this file uses the invalidated extrainfo, we must remove it
                    os.remove(trophyfile)
                    ascfile = trophyfile + ".asc"
                    try:
                        open(ascfile)
                        os.remove(ascfile)
                    except IOError:
                        pass
            
    def get_extra_information(self, app, item):
        extrainfopath = os.path.join(self.trophies_path, ".extrainformation/")
        authfile = os.path.join(extrainfopath, item)
        label = None
        
        for l in self.accomlangs:
            if app in l:
                lang = l[app]
        
        #BROKEN:
        #appdir = os.path.join(self.accomplishments_path, app)
        extrad = os.path.join(appdir, "extrainformation")
        itempath = os.path.join(extrad, item)
        cfg = ConfigParser.RawConfigParser()
        cfg.read(itempath)
        if cfg.has_option("label", self.lang):
            label = cfg.get("label", self.lang)
        else:
            label = cfg.get("label", "en")
        
        log.msg("The authfile is %s" % authfile)
        
        try:
            f = open(authfile, "r")
            data = f.read()
            final = [{item : data, "label" : label}]
        except IOError as e:
            #print "No data."
            final = [{item : False, "label" : ""}]
        return final
		
    # =================================================================
        
    def reload_accom_database(self):
    
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
                        del accomdata['__name__']
                        accomdata['type'] = "accomplishment"
                        accomdata['lang'] = langused
                        accomdata['base-path'] = collpath
                        accomdata['script-path'] = os.path.join(installpath,os.path.join('scripts',os.path.join(collection,accomset[:-15] + ".py")))
                        self.accDB[accomID] = accomdata
                        accno = accno + 1
                    else:
                        # this is indeed a set!
                        setID = collection + "/" + accomset
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
                            accomID = collection + "/" + accomset + "/" + accomfile[:-15]
                            accomdata['type'] = "accomplishment"
                            del accomdata['__name__']
                            accomdata['lang'] = langused
                            accomdata['base-path'] = collpath
                            accomdata['script-path'] = os.path.join(installpath,os.path.join('scripts',os.path.join(collection,os.path.join(accomset,accomfile[:-15] + ".py"))))
                            self.accDB[accomID] = accomdata
                            accno = accno + 1
                            
                # Store data about this colection
                collectiondata = {'langdefault':langdefault,'name':collectionname, 'acc_num':accno, 'type':"collection"}
                self.accDB[collection] = collectiondata
          
        # Uncomment following for debugging
        print self.accDB
        
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
        elif (self.accDB[accomID][needs-signing] == "false" or self.accDB[accomID][needs-signing] == "False" or self.accDB[accomID][needs-signing] == "no"):
            return False
        else:
            return True
    
    def get_acc_depends(self,accomID):
        if 'depends' in self.accDB[accomID]:
            return self.accDB[accomID]['depends']
        else:
            return
    
    def get_acc_is_unlocked(self,accomID):
        dependency = self.get_acc_depends(accomID)
        if not dependency:
            return True
        else:
            return self.get_acc_is_completed(dependency)
    
    def get_trophy_path(self,accomID):
        if not self.get_acc_exists(accomID):
            # hopefully an empty path will break something...
            return ""
        else:
            return os.path.join(self.trophies_path,accomID + ".trophy")

    def get_acc_is_completed(self,accomID):
        trophypath = self.get_trophy_path(accomID)
        if not os.path.exists(trophypath):
            return False
        if not self.get_acc_needs_signing(accomID):
            return True
        else:
            return self._get_is_asc_correct(trophypath + ".asc")
        
    def get_acc_script_path(self,accomID):
        return self.accDB[accomID]['script-path']
        
    def get_acc_icon(self,accomID):
        return self.accDB[accomID]['icon']
        
    def get_acc_icon_path(self,accomID):
        return os.path.join(self.accDB[accomID]['base-path'], os.path.join('trophyimages',self.get_acc_icon(accomID)))
    
    def get_acc_needs_info(self,accomID):
        if not 'needs-information' in self.accDB[accomID]:
            return []
        return self.accDB[accomID]['needs-information'].split(" ")
    
    def get_trophy_data(self,accomID):
        if not self.get_acc_is_completed(accomID):
            return
        else:
            cfg = ConfigParser.RawConfigParser()
            cfg.read(self.get_trophy_path(accomID))
            return dict(accomcfg._sections["trophy"])
    
    def get_collection_name(self,collection):
        return self.accDB[collection]['name']
        
    # ====== Listing functions ======
    
    def list_accomplishments(self):
        return [acc for acc in self.accomslist()]
        
    def list_trophies(self):
        return [acc for acc in self.accomslist() if self.get_acc_is_completed(acc)]
        
    def list_opportunitues(self):
        return [acc for acc in self.accomslist() if not self.get_acc_is_completed(acc)]
        
    def list_depending_on(self,accomID):
        return [acc for acc in self.accomslist() if self.get_acc_depends(acc) == accomID]
        
    def list_unlocked(self):
        return [acc for acc in self.accomslist() if self.get_acc_is_unlocked(acc)]
        
    def list_unlocked_not_completed(self):
        return [acc for acc in self.accomslist() if self.get_acc_is_unlocked(acc) and not self.get_acc_is_completed(acc)]        
    
    # ================================
    
    def accomplish(self,accomID):
        log.msg("Accomplishing: %s", accomID)
        if not self.get_acc_exists(accomID):
            log.msg("There is no such accomplishment.")
            return False
            
        coll = self._coll_from_accomID(accomID)
        accdata = self.get_acc_data(accomID)
        
        # Check if this accomplishment is unlocked
        if not self.get_acc_is_unlocked(accomID):
            log.msg("This accomplishment cannot be completed; it's locked.")
            return False
        
        # Prepare extra-info
        needsinformation = self.get_acc_needs_info(accomID)
        for i in needsinformation:
            accdata[i] = self.get_extra_information(coll,i)
            
        # Create .trophy file
        cp = ConfigParser.RawConfigParser()
        cp.add_section("trophy")
        cp.set("trophy", "accomplishment", accomID)
        for i, v in accdata.items():
            cp.set("trophy", i, v)
        now = datetime.datetime.now()
        cp.set("trophy", "date-accomplished", now.strftime("%Y-%m-%d %H:%M"))
        trophypath = self.get_trophy_path(accomID)
        dirpath = os.path.split(trophypath)[0]
        if not os.path.exists(dirpath):
            os.makedirs(dirpath)
        fp = open(trophypath, "w")
        cp.write(fp)
        fp.close()
        
        if not self.get_acc_needs_signing():
            # The accomplishment does not need signing!
            self.service.trophy_received("accomID")
            self._display_accomplished_bubble("accomID")
            self._display_unlocked_bubble("accomID")
            self.run_all_scripts()
            
        return True
        
    def run_script(self,accomID):
        # Schedules a single script to be run
        pass
        pass
        pass
        
    def run_all_scripts(self):
        to_run = self.list_unlocked_not_completed()
        for acc in to_run:
            run_script(acc)
        
    def _coll_from_accomID(self,accomID):
        return accomID.split("/")[0]
    
    def _display_accomplished_bubble(self,accomID):
        if self.show_notifications == True and pynotify and (
            pynotify.is_initted() or pynotify.init("icon-summary-body")):
            n = pynotify.Notification(
                _("You have accomplished something!"),
                self.get_acc_title(accomID),
                self.get_acc_icon_path(accomID) )
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
            log.msg("Cannot check if signature is correct, because file %s does not exist", filepath)
            return False
