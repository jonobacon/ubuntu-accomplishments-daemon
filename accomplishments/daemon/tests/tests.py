"""
Tests for accomplishments daemon.
"""
import unittest
import sys, os
import tempfile
import shutil
import subprocess
import ConfigParser

sys.path.insert(0, os.path.join(os.path.split(__file__)[0], "../../.."))
from accomplishments.daemon import app, api

# future tests
# bad accomplishment shouldn't show in the list
# get all extra information
# get all extra information required
# create extra information files
# invalidate extra information
# get extra information
# get acc data
# get acc exists
# get acc title
# get acc needs signing
# get acc depends
# get acc isunlocked
# get trophy path
# get acc is completed
# get acc script path
# get acc needs info
# get acc collection
# get acc categories
# get acc date completed
# get trophy data
# get collection name
# get collection exists
# get collection authors
# get collection categories
# get collection data
# list trophies
# list opportunities
# list depending on
# list unlocked
# list unlocked not completed
# list collections
# run scripts/runscript
# build viewer database
# get published status
# set daemon session start
# get daemon session start
# set block u1 notification bubbles
# get block u1 notification bubbles

class TestDaemon(unittest.TestCase):

    ACCOMP_SET = "testaccomp"
    LANG = "en"

    def util_write_about_file(self, accomp_dir):
        fp = open(os.path.join(accomp_dir, "ABOUT"), "w")
        fp.write("""[general]
name = Test Collection
langdefault=%s""" % self.LANG)
        fp.close()

    def util_write_config_file(self, accomp_dir):
        fp = open(os.path.join(accomp_dir, ".accomplishments"), "w")
        fp.write("""[config]
has_u1 = true
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

        # XXX - not sure this is correct
        # /tmp/foo/accomplishments/scripts/testaccomp/trophies
        self.trophy_dir = os.path.join(self.td, "trophies")
        if not os.path.exists(self.trophy_dir):
            os.makedirs(self.trophy_dir)

        #self.util_write_file(self.script_root, "third.py", "print 'hello'")

        self.util_write_about_file(self.accomp_root)

        self.util_write_config_file(self.config_dir)

        os.environ['ACCOMPLISHMENTS_ROOT_DIR'] = self.td

    def tearDown(self):
        del os.environ['ACCOMPLISHMENTS_ROOT_DIR']
        shutil.rmtree(self.td)

    def test_get_media_file(self):
        a = api.Accomplishments(None)
        mf = a.get_media_file("non-existant.jpg")
        self.assertTrue(mf == None)

        mf = a.get_media_file("lock.png")
        self.assertTrue(mf.endswith("lock.png"))

    def test_get_API_version(self):
        a = api.Accomplishments(None)
        version = a.get_API_version()
        self.assertTrue(isinstance(version, basestring))

    # also tests get_acc_icon_path
    def test_get_acc_icon(self):
        self.util_write_file(self.accomp_dir, "first.accomplishment",
            "[accomplishment]\n"\
            "title=My First Accomplishment\n"\
            "icon=test.jpg\n"\
            "description=An example accomplishment for the test suite\n")
        a = api.Accomplishments(None)
        self.assertEquals(a.get_acc_icon('%s/first' % self.ACCOMP_SET),
           'test.jpg')
        icon_path = a.get_acc_icon_path('%s/first' % self.ACCOMP_SET)
        self.assertTrue(icon_path.endswith("test-opportunity.jpg"))

    def test_build_viewer_database(self):
        self.util_write_file(self.accomp_dir, "first.accomplishment",
            "[accomplishment]\n"\
            "title=My First Accomplishment\n"\
            "icon=test.jpg\n"\
            "description=An example accomplishment for the test suite\n")

        self.util_write_file(self.accomp_dir, "second.accomplishment",
            "[accomplishment]\n"\
            "title=My Second Accomplishment\n"\
            "icon=test.jpg\n"\
            "description=example for the test suite, with dependency\n"\
            "depends=%s/first\n" % (self.ACCOMP_SET))
        a = api.Accomplishments(None)
        viewer_db = a.build_viewer_database()
        self.assertEquals(len(viewer_db), 2)

        # these match what is in the ABOUT file
        self.assertEquals(viewer_db[0]['collection-human'],
            "Test Collection")
        self.assertEquals(viewer_db[1]['collection-human'],
            "Test Collection")

        # test a few random fields
        for item in viewer_db:
            if item['title'] == "My First Accomplishment":
                self.assertTrue("opportunity" in item['iconpath'])
                self.assertTrue(item['id'] == "%s/first" % self.ACCOMP_SET)
            elif item['title'] == "My Second Accomplishment":
                self.assertTrue("locked" in item['iconpath'])
                self.assertTrue(item['id'] == "%s/second" % self.ACCOMP_SET)
            # this shouldn't happen
            else:
                self.assertTrue(False)

    # also tests reloading the database
    def test_list_all(self):
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
        a = api.Accomplishments(None)
        self.assertEqual(len(a.list_accomplishments()), 3)

        # add a new accomp
        self.util_write_file(self.accomp_dir, "fourth.accomplishment",
            "[accomplishment]\n"\
            "title=My Fourth Accomplishment\n"\
            "description=An example accomplishment for the test suite\n")
        self.assertEqual(len(a.list_accomplishments()), 3)
        a.reload_accom_database()
        self.assertEqual(len(a.list_accomplishments()), 4)

        # remove the new accomp
        os.remove(os.path.join(self.accomp_dir, "fourth.accomplishment"))
        a.reload_accom_database()
        self.assertEqual(len(a.list_accomplishments()), 3)

    @unittest.skip("need the daemon running")
    def test_accomplish(self):
        a = api.Accomplishments(None)
        self.assertEqual(len(a.list_trophies()), 0)
        a.accomplish("%s/first" % self.ACCOMP_SET)
        trophies = a.list_trophies()
        self.assertEqual(len(trophies), 1)
        self.assertEqual(trophies[0]["title"], "My First Accomplishment")

    def test_missing_about_file(self):
        os.remove(os.path.join(self.accomp_root, "ABOUT"))
        self.assertRaises(LookupError, api.Accomplishments, (None))

        # put the file back
        self.util_write_about_file(self.accomp_root)

    def test_bad_accomplishment_parse(self):
        self.util_write_file(self.accomp_dir, "bad.accomplishment",
            "[accomplishment]\n"\
            "descriptionbad desc\n")
        self.assertRaises(ConfigParser.ParsingError, api.Accomplishments,(None))
        os.remove(os.path.join(self.accomp_dir, "bad.accomplishment"))

        self.util_write_file(self.accomp_dir, "bad.accomplishment",
            "[accomplishment]\n"\
            "titlewhatever\n"\
            "description=bad desc\n")
        self.assertRaises(ConfigParser.ParsingError, api.Accomplishments,(None))
        os.remove(os.path.join(self.accomp_dir, "bad.accomplishment"))

    # also tests get_config_value()
    def test_write_config_file_item(self):
        a = api.Accomplishments(None)
        a.write_config_file_item('config', 'has_verif', False)
        self.assertEquals(a.get_config_value('config', 'has_verif'), False)
        self.assertEqual(a.has_verif, False)
        a.write_config_file_item('config', 'has_verif', True)
        self.assertEquals(a.get_config_value('config', 'has_verif'), True)
        self.assertEqual(a.has_verif, True)

        a.write_config_file_item('config', 'trophypath', '/tmp')
        self.assertEquals(a.get_config_value('config', 'trophypath'), '/tmp')
        self.assertEqual(a.trophies_path, '/tmp')

        # restore the original
        self.util_write_config_file(self.config_dir)
        return

if __name__ == "__main__":
    unittest.main()
