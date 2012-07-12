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
# get_acc_date_completed - needs accomplish() to work to be useful
# get all extra information
# get all extra information required
# create extra information files
# invalidate extra information
# get extra information
# get trophy path
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

# These tests will modify the user's envrionment, outside of the test
# dir and so are not written/skipped:
#  - set daemon session start
#  - set block u1 notification bubbles

class TestDaemon(unittest.TestCase):

    ACCOMP_SET = "testaccomp"
    LANG = "en"

    def util_copy_accomp(self, accomp_dir, accomp_name):
        src = os.path.join("accomps", "%s.accomplishment" % accomp_name)
        dest = os.path.join(accomp_dir, "%s.accomplishment" % accomp_name)
        shutil.copyfile(src, dest)

    def util_remove_all_accomps(self, accomp_dir):
        for f in os.listdir(accomp_dir):
            os.remove(os.path.join(self.accomp_dir, f))

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

        # /tmp/foo/accomplishments/accomplishments/scripts
        self.scripts_root = os.path.join(self.td, "accomplishments", "scripts")
        if not os.path.exists(self.scripts_root):
            os.makedirs(self.scripts_root)

        # /tmp/foo/accomplishments/accomplishments/scripts/testaccomp
        self.script_root = os.path.join(self.scripts_root, self.ACCOMP_SET)
        if not os.path.exists(self.script_root):
            os.makedirs(self.script_root)

        # XXX - not sure this is correct or needed
        # /tmp/foo/accomplishments/accomplishments/testaccomp/trophies
        self.trophy_dir = os.path.join(self.td, "trophies")
        if not os.path.exists(self.trophy_dir):
            os.makedirs(self.trophy_dir)

        self.util_write_about_file(self.accomp_root)

        self.util_write_config_file(self.config_dir)

        os.environ['ACCOMPLISHMENTS_ROOT_DIR'] = self.td

    def tearDown(self):
        del os.environ['ACCOMPLISHMENTS_ROOT_DIR']
        shutil.rmtree(self.td)

    def test_handle_duplicate_accomplishments(self):
        return

    # tests all the get_acc_* functions, except for:
    # get_acc_icon
    # get_acc_icon_path
    # get_date_completed
    def test_get_acc_all_funcs(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        self.util_copy_accomp(self.accomp_dir, "third")
        a = api.Accomplishments(None)

        # get_acc_data
        data = a.get_acc_data("%s/first" % self.ACCOMP_SET)
        self.assertTrue(isinstance(data, dict))
        self.assertEquals(data['title'], "My First Accomplishment")
        data = a.get_acc_data("%s/third" % self.ACCOMP_SET)
        self.assertTrue(isinstance(data, dict))
        self.assertEquals(data['title'], "My Third Accomplishment")

        # get_acc_exists
        self.assertTrue(a.get_acc_exists("%s/first" % self.ACCOMP_SET))
        self.assertTrue(a.get_acc_exists("%s/second" % self.ACCOMP_SET))
        self.assertTrue(a.get_acc_exists("%s/third" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_exists("%s/something" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_exists("wrong/first"))

        # get_acc_title
        self.assertEquals(a.get_acc_title("%s/first" % self.ACCOMP_SET),
            "My First Accomplishment")
        self.assertEquals(a.get_acc_title("%s/second" % self.ACCOMP_SET),
            "My Second Accomplishment")
        self.assertEquals(a.get_acc_title("%s/third" % self.ACCOMP_SET),
            "My Third Accomplishment")

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_title("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_description
        self.assertTrue("example" in a.get_acc_description("%s/first" %
            self.ACCOMP_SET))
        self.assertTrue("example" in a.get_acc_description("%s/second" %
            self.ACCOMP_SET))
        self.assertTrue("example" in a.get_acc_description("%s/third" %
            self.ACCOMP_SET))

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_description("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_needs_signing
        self.assertFalse(a.get_acc_needs_signing("%s/first" % self.ACCOMP_SET))
        self.assertTrue(a.get_acc_needs_signing("%s/second" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_needs_signing("%s/first" % self.ACCOMP_SET))

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_needs_signing("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_depends
        self.assertTrue(a.get_acc_depends("%s/first" % self.ACCOMP_SET) == [])
        deps = a.get_acc_depends("%s/second" % self.ACCOMP_SET)
        self.assertEquals(len(deps), 1)
        self.assertTrue(deps[0] == "%s/first" % self.ACCOMP_SET)
        self.assertTrue(a.get_acc_depends("%s/third" % self.ACCOMP_SET) == [])

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_depends("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_is_unlocked
        self.assertTrue(a.get_acc_is_unlocked("%s/first" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_is_unlocked("%s/second" % self.ACCOMP_SET))
        self.assertTrue(a.get_acc_is_unlocked("%s/third" % self.ACCOMP_SET))

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_is_unlocked("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_is_completed
        # XXX - when we get the accomplish() code working, make some of these
        # true
        self.assertFalse(a.get_acc_is_completed("%s/first" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_is_completed("%s/second" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_is_completed("%s/third" % self.ACCOMP_SET))

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_is_completed("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_script_path
        self.assertEqual(a.get_acc_script_path("%s/first" % self.ACCOMP_SET),
            None)
        self.assertEqual(a.get_acc_script_path("%s/second" % self.ACCOMP_SET),
            None)
        self.util_write_file(self.script_root, "third.py", "print 'hello'")
        sp = a.get_acc_script_path("%s/third" % self.ACCOMP_SET)
        self.assertTrue(sp.endswith("third.py"))

        try:
            a.get_acc_script_path("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_needs_info
        info = a.get_acc_needs_info("%s/first" % self.ACCOMP_SET)
        self.assertEqual(len(info),2)
        self.assertEqual(info[0], "info")
        self.assertEqual(info[1], "more info")
        self.assertEqual(a.get_acc_needs_info("%s/second" % self.ACCOMP_SET),
            [])
        self.assertEqual(a.get_acc_needs_info("%s/third" % self.ACCOMP_SET),
            [])

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_needs_info("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_collection
        self.assertEqual(a.get_acc_collection("%s/first" % self.ACCOMP_SET),
            self.ACCOMP_SET)
        self.assertEqual(a.get_acc_collection("%s/second" % self.ACCOMP_SET),
            self.ACCOMP_SET)
        self.assertEqual(a.get_acc_collection("%s/third" % self.ACCOMP_SET),
            self.ACCOMP_SET)

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_collection("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)

        # get_acc_categories
        self.assertEqual(a.get_acc_categories("%s/first" % self.ACCOMP_SET), [])
        self.assertEqual(a.get_acc_categories("%s/second" % self.ACCOMP_SET),
            [])
        info = a.get_acc_categories("%s/third" % self.ACCOMP_SET)
        self.assertEqual(len(info),2)
        self.assertEqual(info[0], "testing")
        self.assertEqual(info[1], "unit test")

        # XXX - assertRaises isn't working here the way I think it
        # should, this is a substitute
        try:
            a.get_acc_categories("wrong")
            self.assertTrue(False)
        except KeyError:
            self.assertTrue(True)


    def test_get_block_ubuntuone_notification_bubbles(self):
        a = api.Accomplishments(None)
        val = a.get_block_ubuntuone_notification_bubbles()
        self.assertTrue(isinstance(val, bool))
        # don't write the config file here because it's using U1's
        # config file which will overwrite the user's prefs

    @unittest.skip("this will modify the user's environment, skipping")
    def test_set_block_ubuntuone_notifiction_bubbles(self):
        # there's no current way to test this in /tmp, so we don't do
        # it currently.
        return

    def test_get_daemon_session_start(self):
        a = api.Accomplishments(None)
        val = a.get_daemon_session_start()
        self.assertTrue(isinstance(val, bool))
        a.write_config_file_item('config', 'daemon_sessionstart', False)

    def test_get_block_ubuntuone_notification_bubbles(self):
        a = api.Accomplishments(None)
        val = a.get_block_ubuntuone_notification_bubbles()
        self.assertTrue(isinstance(val, bool))
        # don't write the config file here because it's using U1's
        # config file which will overwrite the user's prefs

    @unittest.skip("this will modify the user's environment, skipping")
    def test_set_block_ubuntuone_notifiction_bubbles(self):
        # there's no current way to test this in /tmp, so we don't do
        # it currently.
        return

    def test_get_daemon_session_start(self):
        a = api.Accomplishments(None)
        val = a.get_daemon_session_start()
        self.assertTrue(isinstance(val, bool))
        a.write_config_file_item('config', 'daemon_sessionstart', False)
        val = a.get_daemon_session_start()
        self.assertFalse(val)
        self.assertEquals(a.get_config_value('config', 'daemon_sessionstart'),
            False)

    @unittest.skip("this will modify the user's environment, skipping")
    def test_set_daemon_session_start(self):
        # there's no current way to test this in /tmp, so we don't do
        # it currently.
        return

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
        self.util_copy_accomp(self.accomp_dir, "first")
        a = api.Accomplishments(None)
        self.assertEquals(a.get_acc_icon('%s/first' % self.ACCOMP_SET),
           'first.jpg')
        icon_path = a.get_acc_icon_path('%s/first' % self.ACCOMP_SET)
        self.assertTrue(icon_path.endswith("first-opportunity.jpg"))

    def test_build_viewer_database(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        a = api.Accomplishments(None)
        viewer_db = a.build_viewer_database()
        self.assertEquals(len(viewer_db), 2)

        # these match what is in the ABOUT file
        self.assertEquals(viewer_db[0]['collection-human'],
            "Test Collection")
        self.assertEquals(viewer_db[1]['collection-human'],
            "Test Collection")

        self.assertEquals(viewer_db[0]['collection'], "testaccomp")
        self.assertEquals(viewer_db[1]['collection'], "testaccomp")

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
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        self.util_copy_accomp(self.accomp_dir, "third")

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

        self.util_remove_all_accomps(self.accomp_dir)

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

    @unittest.skip("waiting for LP:1024041 to be fixed")
    def test_bad_accomplishment_list(self):
        # this test ensures that a bad accompishment doesn't crash the
        # daemon or get into the list

        # ensure a clean start
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        a = api.Accomplishments(None)
        self.assertEqual(len(a.list_accomplishments()), 1)
        self.util_write_file(self.accomp_dir, "bad.accomplishment",
            "[accomplishment]\n"\
            "descriptionbad desc\n")
        a.reload_accom_database()
        self.assertEqual(len(a.list_accomplishments()), 1)

        # cleanup
        self.util_remove_all_accomps(self.accomp_dir)

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
