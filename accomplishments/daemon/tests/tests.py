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

sys.path.append(os.path.join(os.path.split(__file__)[0], ".."))
from accomplishments.daemon import app


class TestDaemon(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()
        os.mkdir(os.path.join(self.td, "accomplishments"))
        os.mkdir(os.path.join(self.td, "accomplishments", "app1"))
        os.mkdir(os.path.join(self.td, "scripts"))
        os.mkdir(os.path.join(self.td, "scripts", "app1"))
        os.mkdir(os.path.join(self.td, "trophies"))
        fp = open(os.path.join(self.td, "accomplishments", "app1",
            "first.accomplishment"), "w")
        fp.write("""[accomplishment]
application=app1
title=My First Accomplishment
description=An example accomplishment for the test suite
""")
        fp.close()
        fp = open(os.path.join(self.td, "accomplishments", "app1",
            "second.accomplishment"), "w")
        fp.write("""[accomplishment]
application=app1
title=My Second Accomplishment
description=Another example accomplishment for the test suite, with dependency
depends=app1/first
""")
        fp.close()
        fp = open(os.path.join(self.td, "accomplishments", "app1",
            "third.accomplishment"), "w")
        fp.write("""[accomplishment]
application=app1
title=My Third Accomplishment
description=Another example accomplishment for the test suite, no dependency
""")
        fp.close()
        fp = open(os.path.join(self.td, "scripts", "app1",
            "third.py"), "w")
        fp.write("""print 'hello'""")
        fp.close()
        self.d = app.Accomplishments(
            accomplishments_path=os.path.join(self.td, "accomplishments"),
            trophies_path=os.path.join(self.td, "trophies"),
            scripts_path=os.path.join(self.td, "scripts"))

    def tearDown(self):
        shutil.rmtree(self.td)

    def test_list_all(self):
        accoms = self.d.listAllAccomplishments()
        self.assertEqual(len(accoms), 3)
        self.assertTrue("title" in accoms[0])
        fn = accoms[0].get("_filename", "")
        self.assertTrue(
            fn.endswith("app1/first.accomplishment") or
            fn.endswith("app1/second.accomplishment") or
            fn.endswith("app1/third.accomplishment"))

    def test_bad_accomplishment_award_rejected(self):
        self.assertRaises(app.NoSuchAccomplishment, self.d.accomplish,
            "app1", "nonexistent")

    def test_accomplish(self):
        self.assertEqual(len(self.d.listAllTrophies()), 0)
        self.d.accomplish("app1", "first")
        trophies = self.d.listAllTrophies()
        self.assertEqual(len(trophies), 1)
        self.assertEqual(trophies[0]["title"], "My First Accomplishment")

    def test_accomplishments_got_or_not(self):
        # First, check that we haven't accomplished anything yet
        got_or_not = self.d.listAllAccomplishmentsAndStatus()
        self.assertEqual(len(got_or_not), 3)
        for accomplishment in got_or_not:
            if accomplishment["_filename"].endswith("first.accomplishment"):
                self.assertEqual(accomplishment["accomplished"], False)
                self.assertEqual(accomplishment["locked"], False)
            elif accomplishment["_filename"].endswith("second.accomplishment"):
                self.assertEqual(accomplishment["accomplished"], False)
                self.assertEqual(accomplishment["locked"], True)
            elif accomplishment["_filename"].endswith("third.accomplishment"):
                self.assertEqual(accomplishment["accomplished"], False)
                self.assertEqual(accomplishment["locked"], False)
            else:
                # shouldn't happen
                self.assert_("Found an accomplishment that shouldn't exist")

        # And now accomplish one
        self.d.accomplish("app1", "third")
        # Now, first should be unaccomplished but available, second should
        # be unaccomplished and locked (because first is not accomplished),
        # and third is accomplished
        got_or_not = self.d.listAllAccomplishmentsAndStatus()
        self.assertEqual(len(got_or_not), 3)
        for accomplishment in got_or_not:
            if accomplishment["_filename"].endswith("first.accomplishment"):
                self.assertEqual(accomplishment["accomplished"], False)
                self.assertEqual(accomplishment["locked"], False)
            elif accomplishment["_filename"].endswith("second.accomplishment"):
                self.assertEqual(accomplishment["accomplished"], False)
                self.assertEqual(accomplishment["locked"], True)
            elif accomplishment["_filename"].endswith("third.accomplishment"):
                self.assertEqual(accomplishment["accomplished"], True)
                self.assertEqual(accomplishment["locked"], False)
            else:
                # shouldn't happen
                self.assert_("Found an accomplishment that shouldn't exist")

    def test_cannot_accomplished_locked(self):
        self.assertRaises(app.AccomplishmentLocked, self.d.accomplish, "app1", "second")

    def test_all_available_accomplishments_with_scripts(self):
        asa = self.d.listAllAvailableAccomplishmentsWithScripts()
        self.assertEqual(len(asa), 1)
        self.assertTrue(asa[0]["_filename"].endswith("third.accomplishment"))
        self.assertTrue(asa[0]["_script"].endswith("third.py"))

class TestDaemonDBus(TestDaemon):
    def setUp(self):
        TestDaemon.setUp(self)
        env = os.environ.copy()
        path = os.path.join(os.path.split(__file__)[0], "..", "app.py")
        self.p = subprocess.Popen(['python', path,
            "--accomplishments-path=%s" % os.path.join(self.td, "accomplishments"),
            "--trophies-path=%s" % os.path.join(self.td, "trophies"),
            "--scripts-path=%s" % os.path.join(self.td, "scripts"),
            "--suppress-notifications"
            ], env=env)
        # Wait for the service to become available
        time.sleep(1)
        assert self.p.stdout == None
        assert self.p.stderr == None
        obj = dbus.SessionBus().get_object("org.ubuntu.accomplishments", "/")
        self.d = dbus.Interface(obj, "org.ubuntu.accomplishments")

    def test_bad_accomplishment_award_rejected(self):
        self.assertRaises(dbus.DBusException, self.d.accomplish,
            "app1", "nonexistent")

    def test_cannot_accomplished_locked(self):
        self.assertRaises(dbus.DBusException, self.d.accomplish, "app1", "second")

    def tearDown(self):
        os.kill(self.p.pid, 15)
        TestDaemon.tearDown(self)

if __name__ == "__main__":
    unittest.main()

