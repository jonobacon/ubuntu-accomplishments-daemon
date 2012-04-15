"""The libaccomplishments daemon

Provides a D-Bus API to record accomplishments as achieved (trophies) and
to enumerate achieved and unachieved accomplishments.
"""
import gettext
from gettext import gettext as _
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
import sys
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
from accomplishments.util.paths import media_dir, module_dir1, module_dir2, installed

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
        accomname = os.path.splitext(os.path.splitext(
            os.path.split(path)[1])[0])[0]
        data = self.parent.listAccomplishmentInfo(accomname)
        iconpath = os.path.join(
            self.parent.accomplishments_path,
            data[0]["application"],
            "trophyimages",
            data[0]["icon"])

        item = os.path.split(path)[1][:-11]
        app = os.path.split(os.path.split(path)[0])[1]
        data = self.parent.listAccomplishmentInfo(item)

        self.parent.service.trophy_received("foo")
        if self.parent.show_notifications == True and pynotify and (
        pynotify.is_initted() or pynotify.init("icon-summary-body")):
            trophy_icon_path = "file://%s" % os.path.realpath(
                os.path.join(
                    os.path.split(__file__)[0],
                    "trophy-accomplished.svg"))
            n = pynotify.Notification(
                _("You have accomplished something!"), data[0]["title"], iconpath)
            n.show()

        if self.parent.scriptrun_total == len(self.parent.scriptrun_results):
            self.parent.show_unlocked_accomplishments()

        self.parent.run_scripts(0)
        self.wait_until_a_sig_file_arrives()
        #reload_trophy_corresponding_to_sig_file(path)

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
        accoms = self.parent.listAllAvailableAccomplishmentsWithScripts()
                
        totalscripts = len(accoms)
        self.parent.scriptrun_total = totalscripts
        log.msg("Need to run (%d) scripts" % totalscripts)

        scriptcount = 1
        for accom in accoms:
            msg = "%s/%s: %s" % (scriptcount, totalscripts, accom["_script"])
            log.msg(msg)
            exitcode = yield self.run_a_subprocess([accom["_script"]])
            if exitcode == 0:
                self.parent.scriptrun_results.append(
                    str(accom["application"]) + "/"
                    + str(accom["accomplishment"]))
                self.parent.accomplish(
                    accom["application"], accom["accomplishment"])
                log.msg("...Accomplished")
            elif exitcode == 1:
                self.parent.scriptrun_results.append(None)
                log.msg("...Not Accomplished")
            elif exitcode == 2:
                self.parent.scriptrun_results.append(None)
                log.msg("....Error")
            elif exitcode == 4:
                self.parent.scriptrun_results.append(None)
                log.msg("...Could not get launchpad email")
            else:
                self.parent.scriptrun_results.append(None)
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
        self.accomplishments_path = None
        self.scripts_path = None
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
        self.scriptrun_total = 0
        self.scriptrun_results = []
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

        log.msg(
            "------------------- Ubuntu Accomplishments Daemon Log - %s "
            "-------------------", str(datetime.datetime.now()))

        self._loadConfigFile()

        log.msg("Accomplishments path: " + self.accomplishments_path)
        log.msg("Scripts path: " + self.scripts_path)
        log.msg("Trophies path: " + self.trophies_path)

        self.show_notifications = show_notifications
        log.msg("Connecting to Ubuntu One")
        self.sd = SyncDaemonTool()

        # XXX this wait-until thing should go away; it should be replaced by a
        # deferred-returning function that has a callback which fires off
        # generate_all_trophis and schedule_run_scripts...
        self.asyncapi.wait_until_a_sig_file_arrives()
        self.generate_all_trophies()


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

    def show_unlocked_accomplishments(self):
        """
        Determine if accomplishments have been unlocked and display a
        notify-osd bubble.
        """
        unlocked = 0
        it = 0
        for dep in self.depends:
            for res in self.scriptrun_results:
                if dep.values()[0] == res:
                    unlocked = unlocked + 1
            it = it + 1

        if unlocked is not 0:
            if self.show_notifications == True and pynotify and (
            pynotify.is_initted() or pynotify.init("icon-summary-body")):
                #trophy_icon_path = "file://%s" % os.path.realpath(
                #    os.path.join(
                #        os.path.split(__file__)[0], "trophy-accomplished.svg")
                if unlocked == 1:
                    message = "You have unlocked one new accomplishment."
                else:
                    message = "You have unlocked %s new accomplishments." % (
                        str(unlocked))
                n = pynotify.Notification(
                    "Accomplishments Unlocked!", message,
                    self.get_media_file("unlocked.png"))
                n.show()

        self.scriptrun_total = 0
        self.scriptrun_results = []
        self.depends = []

    def _get_accomplishments_files_list(self):
               
        # get list of accomplishments sets
        sets = os.listdir(self.accomplishments_path)
                
        setpaths = []
        
        self.accomlangs = []
        
        log.msg("Checking accomplishment sets for language support:")
        for s in sets:
            log.msg("...checking: " + s)
            langs = os.listdir(os.path.join(self.accomplishments_path, s))
            langs.remove("trophyimages")
            langs.remove("extrainformation")
            langs.remove("ABOUT")
            if self.lang in langs:
                log.msg("......found system language: " + self.lang)
                # here the system language matches a translation in the set
                setpaths.append(
                    os.path.join(self.accomplishments_path, s, self.lang, "*.accomplishment"))
                self.accomlangs.append({ s : self.lang })
                pass
            elif self.lang[:2] in langs:
                log.msg("......found general system language: " + self.lang[:2])
                # here the first letters (e.g. en) are in the accom set
                setpaths.append(
                    os.path.join(
                        os.path.join(
                            os.path.join(self.accomplishments_path, s),
                        self.lang[:2]),
                    "*.accomplishment"))
                self.accomlangs.append({ s : self.lang[:2] })
                pass
            elif self.lang not in langs:
                # here nothing is found so check the default from the
                # ABOUT file in the set
                log.msg("......accomplishment set not found in: " + self.lang)
                aboutfile = os.path.join(
                    os.path.join(self.accomplishments_path, s), "ABOUT")
                config = ConfigParser.RawConfigParser()
                config.read(aboutfile)
                lang = config.get("general", "langdefault")
                log.msg("......loading the set's default language: " + lang)
                setpaths.append(
                    os.path.join(
                        os.path.join(
                            os.path.join(self.accomplishments_path, s),
                        lang),
                    "*.accomplishment"))
                self.accomlangs.append({ s : lang })
                
        finalpaths = []
        
        for p in setpaths:
            log.msg("Looking for accomplishments files in "
                         + os.path.split(p)[0])
            finalpaths = finalpaths + glob.glob(p)

        log.msg(setpaths)
        return finalpaths

    def _get_trophies_files_list(self):
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

    def validate_trophy(self, filename):
        """
        Validated a trophy file to ensure it has not been tampered with.
        Returns True for valid or False for invalid (missing file, bad sig
        etc).
        """
        log.msg("Validate trophy: " + str(filename))

        if os.path.exists(filename):
            # the .asc signed file exists, so let's verify that it is correctly
            # signed by the Matrix
            trophysigned = open(filename, "r")
            trophy = open(filename[:-4], "r")
            c = gpgme.Context()

            signed = StringIO(trophysigned.read())
            plaintext = StringIO(trophy.read())
            sig = c.verify(signed, None, plaintext)

            if len(sig) != 1:
                log.msg("...No Sig")
                return False

            if sig[0].status is not None:
                log.msg("...Bad Sig")
                return False
            else:
                result = {'timestamp': sig[0].timestamp, 'signer': sig[0].fpr}
                log.msg("...Verified!")
                return True
        else:
            log.msg(".asc does not exist for this trophy")
            return False

        log.msg("Verifying trophy signature")

    def _load_trophy_file(self, f):
        log.msg("Load trophy file: " + f)
        config = ConfigParser.RawConfigParser()
        config.read(f)
        data = dict(config._sections["trophy"])
        data["_filename"] = f
        data["accomplishment"] = os.path.splitext(os.path.split(f)[1])[0]
        return data

    def listAllAccomplishments(self):
        log.msg("List all accomplishments")
        log.msg(files)
        fs = [self._load_accomplishment_file(f) for f in
            self._get_accomplishments_files_list()]
        return fs

    def generate_all_trophies(self):
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
            self.generate_trophy_images(
                app_trophyimagespath, cache_trophyimagespath, lock_image_path)

    def reduce_trophy_opacity(self, im, opacity):
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

    def generate_trophy_images(self, infolder, outfolder, watermark):
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
                    reduced = self.reduce_trophy_opacity(im, 1.0)
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

    def verifyU1Account(self):
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

    def getConfigValue(self, section, item):
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

    def setConfigValue(self, section, item, value):
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

        self._loadConfigFile()

    def _writeConfigFile(self):
        log.msg("Writing the configuration file")
        homedir = os.getenv("HOME")
        config = ConfigParser.RawConfigParser()
        cfile = self.dir_config + "/.accomplishments"

        config.add_section('config')

        config.set('config', 'has_u1', self.has_u1)
        config.set('config', 'has_verif', self.has_verif)
        config.set('config', 'accompath', self.accomplishments_path)
        config.set('config', 'trophypath', self.trophies_path)

        with open(cfile, 'wb') as configfile:
        # Writing our configuration file to 'example.cfg'
            config.write(configfile)

        self.accomplishments_path = os.path.join(
            self.accomplishments_path, "accomplishments")
        log.msg("...done.")

    def accomplish(self, app, accomplishment_name):
        log.msg(self.accomlangs)
        for l in self.accomlangs:
            if app in l:
                lang = l[app]
        log.msg(
            "Accomplishing something: %s, %s", app, accomplishment_name)
        accom_file = os.path.join(self.accomplishments_path, app, lang,
            "%s.accomplishment" % accomplishment_name)
        try:
            data = self._load_accomplishment_file(accom_file)
        except KeyError:
            raise exceptions.NoSuchAccomplishment()

        needsinfolist = []

        for k in data:
            if "needs-information" in k:
                needsinfolist.append(data[k])

        for n in needsinfolist:
            values = self.getExtraInformation(app, n)
            data[n] = values[0][n]

        if "depends" in data:
            for dependency in data["depends"].split(","):
                dapp, dname = dependency.split("/")
                dtrophy_file = os.path.join(
                    self.trophies_path, dapp,
                    "%s.trophy.asc" % dname)
                if not os.path.exists(dtrophy_file):
                    raise exceptions.AccomplishmentLocked()

        cp = ConfigParser.RawConfigParser()
        cp.add_section("trophy")
        del data["_filename"]
        cp.set("trophy", "accomplishment", "%s/%s" % (
            app, accomplishment_name))
        for o, v in data.items():
            cp.set("trophy", o, v)
        now = datetime.datetime.now()
        cp.set("trophy", "date-accomplished", now.strftime("%Y-%m-%d %H:%M"))
        try:
            os.makedirs(os.path.join(self.trophies_path, app))
        except OSError:
            pass # already exists
        trophy_file = os.path.join(self.trophies_path, app,
            "%s.trophy" % accomplishment_name)
        fp = open(trophy_file, "w")
        cp.write(fp)
        fp.close()
        
        if data.has_key("needs-signing") == False or data["needs-signing"] is False:
            #self.service.trophy_received()
            if self.show_notifications is True and pynotify and (
            pynotify.is_initted() or pynotify.init("icon-summary-body")):
                # XXX: need to fix loading the right icon
                trophy_icon_path = "file://%s" % os.path.realpath(
                    os.path.join(media_dir, "unlocked.png"))
                n = pynotify.Notification(_("You have accomplished something!"),
                    data["title"], trophy_icon_path)
                n.show()
        else:
            # if the trophy needs signing we wait for wait_until_a_sig_file_arrives
            # to display the notification
            pass
            
        return self._load_trophy_file(trophy_file)

    def _loadConfigFile(self):
        homedir = os.environ["HOME"]
        config = ConfigParser.RawConfigParser()
        cfile = os.path.join(self.dir_config, ".accomplishments")

        u1ver = self.verifyU1Account()

        if u1ver is False:
            self.has_u1 = False
        else:
            self.has_u1 = True

        if config.read(cfile):
            log.msg("Loading configuration file: " + cfile)
            if config.get('config', 'accompath'):
                self.accomplishments_path = os.path.join(
                    config.get('config', 'accompath'), "accomplishments/")
                log.msg(
                    "...setting accomplishments path to: "
                    + self.accomplishments_path)
                self.scripts_path = os.path.split(
                    os.path.split(self.accomplishments_path)[0])[0] + "/scripts"
                log.msg(
                    "...setting scripts path to: " + self.scripts_path)
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
            accompath = os.path.join(homedir, "accomplishments")
            log.msg("Configuration file not found...creating it!")

            self.has_verif = False
            self.accomplishments_path = accompath
            log.msg(
                "...setting accomplishments path to: "
                + self.accomplishments_path)
            self.trophies_path = os.path.join(self.dir_data, "trophies")
            log.msg("...setting trophies path to: " + self.trophies_path)
            self.scripts_path = os.path.join(accompath, "scripts")
            log.msg("...setting scripts path to: " + self.scripts_path)

            if not os.path.exists(self.trophies_path):
                os.makedirs(self.trophies_path)

            self._writeConfigFile()

    def getAllExtraInformation(self):
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
                    label = infoconfig.get("description", deflang)
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

    def getAllExtraInformationRequired(self):
        """
        Return a dictionary of all information required for the accomplishments
        to authticate that has not been set yet. Returns {application,
        needs-information, label, description} Returns only these, which value is not set.
        """
        #fetch a full list of ExtraInformation
        data = self.getAllExtraInformation()
        #now we need to unsort the data just to output these entries, that have value == ""
        #this way we can return a list of ExtraInformation fields, that have not been setConfigValue
        result = []
        for i in data: #for each ExtraInformation in the full list
            if not i['value']: #if the value string is empty, so this ExtraInformation field have not been yet set
                i.pop('value') #remove the 'value' field (it's empty anyway)
                result.append(i) #add this entry to the resulting list
            #do not add these fields, that have some value
            
        return result

    def listAllAccomplishmentsAndStatus(self):
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
            accompath = os.path.join(
                self.accomplishments_path, data["application"])
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

            # validate all files that have been signed
            if self.validate_trophy(trophysigned) == True:
                data["accomplished"] = True
                data["locked"] = False
                data.update(self._load_trophy_file(trophy_file))
                data["iconpath"] = os.path.join(icondir, icon)
            else:
                if os.path.exists(trophysigned):
                    os.remove(trophysigned)
                    os.remove(trophy_file)
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

                        daccomplishment_file = os.path.join(
                            self.accomplishments_path, dapp, dapplang,
                            "%s.accomplishment" % dname)
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

    def listAllAvailableAccomplishmentsWithScripts(self):
        log.msg("List all accomplishments with scripts")
        available = [accom for accom in self.listAllAccomplishmentsAndStatus()
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

    def listAccomplishmentInfo(self, accomplishment):
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

    def listTrophyInfo(self, trophy):
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

    def createExtraInformationFile(self, app, item, data):
        """Does exactly the same as saveExtraInformationFile(), but it does not
           overwrite any existing data"""
        # XXX this should be removed as we are using saveExtraInformationFile
        log.msg(
            "Creating Extra Information file: %s, %s, %s", app, item, data)
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
            
    def saveExtraInformationFile(self, app, item, data):

        log.msg(
            "Saving Extra Information file: %s, %s, %s", app, item, data)
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
            
    def invalidateExtraInformation(self,extrainfo):
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
            
    def getExtraInformation(self, app, item):
        extrainfopath = os.path.join(self.trophies_path, ".extrainformation/")
        authfile = os.path.join(extrainfopath, item)
        label = None
        
        for l in self.accomlangs:
            if app in l:
                lang = l[app]
        
        appdir = os.path.join(self.accomplishments_path, app)
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
    
    def getApplicationFullName(self,app):
        appaboutpath = os.path.join( os.path.join(self.accomplishments_path, app) , "ABOUT")
        aboutcfg = ConfigParser.RawConfigParser()
        aboutcfg.read(appaboutpath)
        name = aboutcfg.get("general","name")
        return name
    
