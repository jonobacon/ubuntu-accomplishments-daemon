"""
Tests for accomplishments daemon.
"""
import unittest
import sys, os
import tempfile
import shutil
import dbus
import time
import subprocess
import ConfigParser

sys.path.insert(0, os.path.join(os.path.split(__file__)[0], "../../.."))
from accomplishments.daemon import app, api

# future tests
# 1) change config file
# 2) write_config_file_item()
# 4) bad accomplishment shouldn't show in the list

class TestDaemon(unittest.TestCase):

    ACCOMP_SET = "testaccomp"
    LANG = "en"

    def util_write_about_file(self, accomp_dir):
        fp = open(os.path.join(accomp_dir, "ABOUT"), "w")
        fp.write("""[general]
name = Ubuntu Community
langdefault=%s""" % self.LANG)
        fp.close()

    def util_write_config_file(self, accomp_dir):
        fp = open(os.path.join(accomp_dir, ".accomplishments"), "w")
        fp.write("""[config]
has_u1 = True
has_verif = 1
accompath = %s/accomplishments
trophypath = %s/accomplishments/.local/share/accomplishments/trophies
daemon_sessionstart = false
extrainfo_seen = 1""" % (self.td, self.td))
        fp.close()

    def util_write_file(self, accomp_dir, name, content):
        fp = open(os.path.join(accomp_dir, name), "w")
        fp.write(content)
        fp.close()

    def setUp(self):
        self.td = tempfile.mkdtemp()
        self.td = "/tmp/foo"
        print "Test Dir is %s" % self.td

        # /tmp/foo/accomplishments
        self.accomps_root = os.path.join(self.td, "accomplishments",
            "accomplishments")
        if not os.path.exists(self.accomps_root):
            os.makedirs(self.accomps_root)

        # /tmp/foo/accomplishments/accomplishments/.config
        self.config_dir = os.path.join(self.td, "accomplishments", ".config",
            "accomplishments")
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

        # /tmp/foo/accomplishments/accomplishments/testaccomp
        self.accomp_root = os.path.join(self.accomps_root, self.ACCOMP_SET)
        if not os.path.exists(self.accomp_root):
            os.makedirs(self.accomp_root)

        # /tmp/foo/accomplishments/accomplishments/testaccomp/en
        self.accomp_dir = os.path.join(self.accomp_root, self.LANG)
        if not os.path.exists(self.accomp_dir):
            os.makedirs(self.accomp_dir)

        # /tmp/foo/accomplishments/accomplishments/testaccomp/extrainformation
        self.extrainfo_dir = os.path.join(self.accomp_root, "extrainformation")
        if not os.path.exists(self.extrainfo_dir):
            os.makedirs(self.extrainfo_dir)

        # /tmp/foo/accomplishments/scripts
        self.scripts_root = os.path.join(self.td, "scripts")
        if not os.path.exists(self.scripts_root):
            os.makedirs(self.scripts_root)

        # /tmp/foo/accomplishments/scripts/testaccomp
        self.script_root = os.path.join(self.scripts_root, self.ACCOMP_SET)
        if not os.path.exists(self.script_root):
            os.makedirs(self.script_root)

        # XXX ?
        # /tmp/foo/accomplishments/scripts/testaccomp
        self.trophy_dir = os.path.join(self.td, "trophies")
        if not os.path.exists(self.trophy_dir):
            os.makedirs(self.trophy_dir)

        self.util_write_file(self.accomp_dir, "first.accomplishment",
            "[accomplishment]\n"\
            "title=My First Accomplishment\n"\
            "description=An example accomplishment for the test suite\n")

        self.util_write_file(self.accomp_dir, "second.accomplishment",
            "[accomplishment]\n"\
            "title=My Second Accomplishment\n"\
            "description=example for the test suite, with dependency\n"\
            "depends=%s/first\n" % (self.ACCOMP_SET))

        self.util_write_file(self.accomp_dir, "third.accomplishment",
            "[accomplishment]\n"\
            "title=My Third Accomplishment\n"\
            "description=example for the test suite, no dependency\n")

        self.util_write_file(self.script_root, "third.py", "print 'hello'")

        self.util_write_about_file(self.accomp_root)

        self.util_write_config_file(self.config_dir)

        os.environ['ACCOMPLISHMENTS_ROOT_DIR'] = self.td
        self.d = api.Accomplishments(None)

    def tearDown(self):
        del os.environ['ACCOMPLISHMENTS_ROOT_DIR']
#        shutil.rmtree(self.td)

    def test_list_all(self):
        accomps = self.d.list_accomplishments()
        self.assertEqual(len(accomps), 3)
        for accomp in accomps:
            self.assertTrue(
                accomp == "%s/first" % self.ACCOMP_SET or
                accomp == "%s/second" % self.ACCOMP_SET or
                accomp == "%s/third" % self.ACCOMP_SET)

    def test_accomplish(self):
        self.assertEqual(len(self.d.list_trophies()), 0)
        self.d.accomplish("%s/first" % self.ACCOMP_SET)
        trophies = self.d.list_trophies()
        self.assertEqual(len(trophies), 1)
        self.assertEqual(trophies[0]["title"], "My First Accomplishment")

    def test_missing_about_file(self):
        os.remove(os.path.join(self.accomp_root, "ABOUT"))
        self.assertRaises(LookupError, api.Accomplishments, (None))
        self.util_write_about_file(self.accomp_root)

    def test_bad_accomplishment_parse(self):
        self.util_write_file(self.accomp_dir, "bad.accomplishment",
            "[accomplishment]\n"\
            "descriptionbad desc\n")
        self.assertRaises(ConfigParser.ParsingError, api.Accomplishments,(None))
        os.remove(os.path.join(self.accomp_dir, "bad.accomplishment"))

        self.util_write_file(self.accomp_dir, "bad.accomplishment",
            "[foo]\n"\
            "title=whatever\n"\
            "description=bad desc\n")
        self.assertRaises(ConfigParser.ParsingError, api.Accomplishments,(None))
        os.remove(os.path.join(self.accomp_dir, "bad.accomplishment"))

#    def test_accomplishments_got_or_not(self):
#        # First, check that we haven't accomplished anything yet
#        got_or_not = self.d.listAllAccomplishmentsAndStatus()
#        self.assertEqual(len(got_or_not), 3)
#        for accomplishment in got_or_not:
#            if accomplishment["_filename"].endswith("first.accomplishment"):
#                self.assertEqual(accomplishment["accomplished"], False)
#                self.assertEqual(accomplishment["locked"], False)
#            elif accomplishment["_filename"].endswith("second.accomplishment"):
#                self.assertEqual(accomplishment["accomplished"], False)
#                self.assertEqual(accomplishment["locked"], True)
#            elif accomplishment["_filename"].endswith("third.accomplishment"):
#                self.assertEqual(accomplishment["accomplished"], False)
#                self.assertEqual(accomplishment["locked"], False)
#            else:
#                # shouldn't happen
#                self.assert_("Found an accomplishment that shouldn't exist")
#
#        # And now accomplish one
#        self.d.accomplish("app1", "third")
#        # Now, first should be unaccomplished but available, second should
#        # be unaccomplished and locked (because first is not accomplished),
#        # and third is accomplished
#        got_or_not = self.d.listAllAccomplishmentsAndStatus()
#        self.assertEqual(len(got_or_not), 3)
#        for accomplishment in got_or_not:
#            if accomplishment["_filename"].endswith("first.accomplishment"):
#                self.assertEqual(accomplishment["accomplished"], False)
#                self.assertEqual(accomplishment["locked"], False)
#            elif accomplishment["_filename"].endswith("second.accomplishment"):
#                self.assertEqual(accomplishment["accomplished"], False)
#                self.assertEqual(accomplishment["locked"], True)
#            elif accomplishment["_filename"].endswith("third.accomplishment"):
#                self.assertEqual(accomplishment["accomplished"], True)
#                self.assertEqual(accomplishment["locked"], False)
#            else:
#                # shouldn't happen
#                self.assert_("Found an accomplishment that shouldn't exist")
#
#    def test_cannot_accomplished_locked(self):
#        self.assertRaises(app.AccomplishmentLocked, self.d.accomplish, "app1", "second")
#
#    def test_all_available_accomplishments_with_scripts(self):
#        asa = self.d.listAllAvailableAccomplishmentsWithScripts()
#        self.assertEqual(len(asa), 1)
#        self.assertTrue(asa[0]["_filename"].endswith("third.accomplishment"))
#        self.assertTrue(asa[0]["_script"].endswith("third.py"))
#
#class TestDaemonDBus(TestDaemon):
#    def setUp(self):
#        TestDaemon.setUp(self)
#        env = os.environ.copy()
#        path = os.path.join(os.path.split(__file__)[0], "..", "app.py")
#        self.p = subprocess.Popen(['python', path,
#            "--accomplishments-path=%s" % os.path.join(self.td, "accomplishments"),
#            "--trophies-path=%s" % os.path.join(self.td, "trophies"),
#            "--scripts-path=%s" % os.path.join(self.td, "scripts"),
#            "--suppress-notifications"
#            ], env=env)
#        # Wait for the service to become available
#        time.sleep(1)
#        assert self.p.stdout == None
#        assert self.p.stderr == None
#        obj = dbus.SessionBus().get_object("org.ubuntu.accomplishments", "/")
#        self.d = dbus.Interface(obj, "org.ubuntu.accomplishments")
#
#    def test_bad_accomplishment_award_rejected(self):
#        self.assertRaises(dbus.DBusException, self.d.accomplish,
#            "app1", "nonexistent")
#
#    def test_cannot_accomplished_locked(self):
#        self.assertRaises(dbus.DBusException, self.d.accomplish, "app1", "second")
#
#    def tearDown(self):
#        os.kill(self.p.pid, 15)
#        TestDaemon.tearDown(self)
#
if __name__ == "__main__":
    unittest.main()
