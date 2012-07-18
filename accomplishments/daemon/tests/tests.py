"""
Tests for accomplishments daemon.
"""
import unittest
import sys, os
import tempfile
import shutil
import subprocess
import ConfigParser
import datetime

sys.path.insert(0, os.path.join(os.path.split(__file__)[0], "../../.."))
from accomplishments.daemon import app, api

# future tests:
# create extra information files - marked for removal in the code
# run scripts/runscript
# get published status
# invalidate extra information

# These tests will modify the user's envrionment, outside of the test
# dir and so are not written/skipped:
#  - set daemon session start
#  - set block u1 notification bubbles

# Debugging:
# To debug tests, the following changes are recommended:
# 1) comment out the shutil.rmtree in tearDown()
# 2) in setUp, set self.td to a known place, like /tmp/foo (you will need
#    to create this directory as well)

class TestDaemon(unittest.TestCase):

    ACCOMP_SET = "testaccomp"
    LANG = "en"

    def util_copy_extrainfo(self, extrainfo_dir, extrainfo_name):
        testdir = os.path.dirname(__file__)
        src = os.path.join(testdir, "extrainformation", extrainfo_name)
        dest = os.path.join(extrainfo_dir, extrainfo_name)
        shutil.copyfile(src, dest)

    def util_copy_accomp(self, accomp_dir, accomp_name):
        testdir = os.path.dirname(__file__)
        src = os.path.join(testdir, "accomps",
            "%s.accomplishment" % accomp_name)
        dest = os.path.join(accomp_dir, "%s.accomplishment" % accomp_name)
        shutil.copyfile(src, dest)

    # This function is not really needed because when tearDown runs it
    # removes the entire tree, but when debugging tests it's useful to comment
    # out the rmtree in tearDown, so then this is critical to make the tests
    # work.
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

        # /tmp/foo/accomplishments/.local/share/accomplishments/trophies
        self.trophy_dir = os.path.join(self.td, "accomplishments", ".local",
            "share", "accomplishments", "trophies")
        if not os.path.exists(self.trophy_dir):
            os.makedirs(self.trophy_dir)

        self.util_write_about_file(self.accomp_root)

        self.util_write_config_file(self.config_dir)

        os.environ['ACCOMPLISHMENTS_ROOT_DIR'] = self.td

    def tearDown(self):
        del os.environ['ACCOMPLISHMENTS_ROOT_DIR']
        shutil.rmtree(self.td)

    def test_get_acc_date_completed(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        self.util_copy_accomp(self.accomp_dir, "third")
        self.util_copy_extrainfo(self.extrainfo_dir, "info")
        self.util_copy_extrainfo(self.extrainfo_dir, "info2")
        a = api.Accomplishments(None, None, True)
        a.write_extra_information_file("info", "whatever")
        a.write_extra_information_file("info2", "whatever2")

        self.assertTrue(a.accomplish("%s/first" % self.ACCOMP_SET))
        self.assertTrue(a.accomplish("%s/second" % self.ACCOMP_SET))
        self.assertTrue(a.accomplish("%s/third" % self.ACCOMP_SET))

        trophies = a.list_trophies()
        # since "second" requires signing, it shouldn't be listed
        self.assertEqual(len(trophies), 2)

        d1 = a.get_acc_date_completed("%s/first" % self.ACCOMP_SET)
        self.assertTrue(isinstance(d1, basestring))
        dt1 = datetime.datetime.strptime(d1, "%Y-%m-%d %H:%M")
        self.assertTrue(dt1 is not None)

        d3 = a.get_acc_date_completed("%s/third" % self.ACCOMP_SET)
        self.assertTrue(isinstance(d3, basestring))
        dt3 = datetime.datetime.strptime(d3, "%Y-%m-%d %H:%M")
        self.assertTrue(dt3 is not None)

    # this tests:
    # accomplish()
    # list_opportunities
    # list_trophies
    # list_unlocked
    # list_unlocked_not_completed
    # get_trophy_data
    def test_accomplish(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        self.util_copy_accomp(self.accomp_dir, "third")
        a = api.Accomplishments(None, None, True)

        # before accomplishing
        opps = a.list_opportunitues()
        self.assertEqual(len(opps), 3)
        for accom in opps:
            self.assertTrue(accom in ["%s/first" % self.ACCOMP_SET,
                "%s/second" % self.ACCOMP_SET, "%s/third" % self.ACCOMP_SET])

        unlocked = a.list_unlocked()
        self.assertEqual(len(unlocked), 2)
        for accom in unlocked:
            self.assertTrue(accom in ["%s/first" % self.ACCOMP_SET,
                "%s/third" % self.ACCOMP_SET])

        unlocked_nc = a.list_unlocked_not_completed()
        self.assertEqual(len(unlocked_nc), 2)
        for accom in unlocked_nc:
            self.assertTrue(accom in ["%s/first" % self.ACCOMP_SET,
                "%s/third" % self.ACCOMP_SET])

        trophies = a.list_trophies()
        self.assertEqual(len(trophies), 0)

        self.assertTrue(a.get_trophy_data("%s/first" % self.ACCOMP_SET) is None)
        self.assertTrue(a.get_trophy_data("%s/second" % self.ACCOMP_SET)
            is None)
        self.assertTrue(a.get_trophy_data("%s/third" % self.ACCOMP_SET) is None)

        # now let's accomplish something, it should fail without extra info
        self.assertRaises(KeyError, a.accomplish, "%s/first" % self.ACCOMP_SET)

        # this time it will work
        self.util_copy_extrainfo(self.extrainfo_dir, "info")
        self.util_copy_extrainfo(self.extrainfo_dir, "info2")
        a.reload_accom_database()
        self.assertTrue(a.accomplish("%s/first" % self.ACCOMP_SET))

        opps = a.list_opportunitues()
        self.assertEqual(len(opps), 2)
        for accom in opps:
            self.assertTrue(accom in ["%s/second" % self.ACCOMP_SET,
                "%s/third" % self.ACCOMP_SET])

        unlocked = a.list_unlocked()
        self.assertEqual(len(unlocked), 3)
        for accom in unlocked:
            self.assertTrue(accom in ["%s/first" % self.ACCOMP_SET,
                "%s/second" % self.ACCOMP_SET,
                "%s/third" % self.ACCOMP_SET])

        unlocked_nc = a.list_unlocked_not_completed()
        self.assertEqual(len(unlocked_nc), 2)
        for accom in unlocked_nc:
            self.assertTrue(accom in ["%s/second" % self.ACCOMP_SET,
                "%s/third" % self.ACCOMP_SET])

        trophies = a.list_trophies()
        self.assertEqual(len(trophies), 1)
        for accom in trophies:
            self.assertTrue(accom in ["%s/first" % self.ACCOMP_SET])

        td = a.get_trophy_data("%s/first" % self.ACCOMP_SET)
        self.assertTrue(isinstance(td, dict))

        self.assertTrue(td['date-accomplished'] is not None)
        self.assertTrue(td['version'] is not None)
        self.assertTrue(td['__name__'] == "trophy")
        self.assertTrue(td['id'] == "%s/first" % self.ACCOMP_SET)
        self.assertTrue(td['needs-information'] is not None)

    def test_list_depending_on(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        self.util_copy_accomp(self.accomp_dir, "third")
        a = api.Accomplishments(None, None, True)

        self.assertEquals(len(a.list_depending_on("%s/first" %
            self.ACCOMP_SET)), 1)
        self.assertEquals(len(a.list_depending_on("%s/second" %
            self.ACCOMP_SET)), 0)
        self.assertEquals(len(a.list_depending_on("%s/third" %
            self.ACCOMP_SET)), 0)

    # tests all the get_acc_* functions, except for:
    # get_acc_icon
    # get_acc_icon_path
    # get_date_completed
    def test_get_acc_all_funcs(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        self.util_copy_accomp(self.accomp_dir, "third")
        a = api.Accomplishments(None, None, True)

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
        self.assertRaises(KeyError, a.get_acc_title, "wrong")

        # get_acc_description
        self.assertTrue("example" in a.get_acc_description("%s/first" %
            self.ACCOMP_SET))
        self.assertTrue("example" in a.get_acc_description("%s/second" %
            self.ACCOMP_SET))
        self.assertTrue("example" in a.get_acc_description("%s/third" %
            self.ACCOMP_SET))
        self.assertRaises(KeyError, a.get_acc_description, "wrong")

        # get_acc_needs_signing
        self.assertFalse(a.get_acc_needs_signing("%s/first" % self.ACCOMP_SET))
        self.assertTrue(a.get_acc_needs_signing("%s/second" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_needs_signing("%s/first" % self.ACCOMP_SET))
        self.assertRaises(KeyError, a.get_acc_needs_signing, "wrong")

        # get_acc_depends
        self.assertTrue(a.get_acc_depends("%s/first" % self.ACCOMP_SET) == [])
        deps = a.get_acc_depends("%s/second" % self.ACCOMP_SET)
        self.assertEquals(len(deps), 1)
        self.assertTrue(deps[0] == "%s/first" % self.ACCOMP_SET)
        self.assertTrue(a.get_acc_depends("%s/third" % self.ACCOMP_SET) == [])
        self.assertRaises(KeyError, a.get_acc_depends, "wrong")

        # get_acc_is_unlocked
        self.assertTrue(a.get_acc_is_unlocked("%s/first" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_is_unlocked("%s/second" % self.ACCOMP_SET))
        self.assertTrue(a.get_acc_is_unlocked("%s/third" % self.ACCOMP_SET))
        self.assertRaises(KeyError, a.get_acc_is_unlocked, "wrong")

        # get_acc_is_completed
        # XXX - when we get the accomplish() code working, make some of these
        # true
        self.assertFalse(a.get_acc_is_completed("%s/first" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_is_completed("%s/second" % self.ACCOMP_SET))
        self.assertFalse(a.get_acc_is_completed("%s/third" % self.ACCOMP_SET))
        self.assertRaises(KeyError, a.get_acc_is_completed, "wrong")

        # get_acc_script_path
        self.assertEqual(a.get_acc_script_path("%s/first" % self.ACCOMP_SET),
            None)
        self.assertEqual(a.get_acc_script_path("%s/second" % self.ACCOMP_SET),
            None)
        self.util_write_file(self.script_root, "third.py", "print 'hello'")
        sp = a.get_acc_script_path("%s/third" % self.ACCOMP_SET)
        self.assertTrue(sp.endswith("third.py"))
        self.assertRaises(KeyError, a.get_acc_script_path, "wrong")

        # get_acc_needs_info
        info = a.get_acc_needs_info("%s/first" % self.ACCOMP_SET)
        self.assertEqual(len(info),2)
        for i in info:
           self.assertTrue(i in ["info", "info2"])
        self.assertEqual(a.get_acc_needs_info("%s/second" % self.ACCOMP_SET),
            [])
        self.assertEqual(a.get_acc_needs_info("%s/third" % self.ACCOMP_SET),
            [])
        self.assertRaises(KeyError, a.get_acc_needs_info, "wrong")

        # get_acc_collection
        self.assertEqual(a.get_acc_collection("%s/first" % self.ACCOMP_SET),
            self.ACCOMP_SET)
        self.assertEqual(a.get_acc_collection("%s/second" % self.ACCOMP_SET),
            self.ACCOMP_SET)
        self.assertEqual(a.get_acc_collection("%s/third" % self.ACCOMP_SET),
            self.ACCOMP_SET)
        self.assertRaises(KeyError, a.get_acc_collection, "wrong")

        # get_acc_categories
        self.assertEqual(a.get_acc_categories("%s/first" % self.ACCOMP_SET), [])
        self.assertEqual(a.get_acc_categories("%s/second" % self.ACCOMP_SET),
            [])
        categories = a.get_acc_categories("%s/third" % self.ACCOMP_SET)
        self.assertEqual(len(info),2)
        for category in categories:
           self.assertTrue(category in ["testing", "unit test"])
        self.assertRaises(KeyError, a.get_acc_categories, "wrong")

    def test_get_block_ubuntuone_notification_bubbles(self):
        a = api.Accomplishments(None, None, True)
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
        a = api.Accomplishments(None, None, True)
        val = a.get_daemon_session_start()
        self.assertTrue(isinstance(val, bool))
        a.write_config_file_item('config', 'daemon_sessionstart', False)
        self.assertFalse(a.get_daemon_session_start())

    @unittest.skip("this will modify the user's environment, skipping")
    def test_set_daemon_session_start(self):
        # there's no current way to test this in /tmp, so we don't do
        # it currently.
        return

    def test_get_media_file(self):
        a = api.Accomplishments(None, None, True)
        mf = a.get_media_file("non-existant.jpg")
        self.assertTrue(mf == None)

        mf = a.get_media_file("lock.png")
        self.assertTrue(mf.endswith("lock.png"))

    def test_get_API_version(self):
        a = api.Accomplishments(None, None, True)
        version = a.get_API_version()
        self.assertTrue(isinstance(version, basestring))

    # also tests get_acc_icon_path
    def test_get_acc_icon(self):
        self.util_copy_accomp(self.accomp_dir, "first")
        a = api.Accomplishments(None, None, True)
        self.assertEquals(a.get_acc_icon('%s/first' % self.ACCOMP_SET),
           'first.jpg')
        icon_path = a.get_acc_icon_path('%s/first' % self.ACCOMP_SET)
        self.assertTrue(icon_path.endswith("first-opportunity.jpg"))

    def test_build_viewer_database(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        a = api.Accomplishments(None, None, True)
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

        a = api.Accomplishments(None, None, True)
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

    def test_missing_about_file(self):
        os.remove(os.path.join(self.accomp_root, "ABOUT"))
        self.assertRaises(LookupError, api.Accomplishments, None, None, True)

        # put the file back
        self.util_write_about_file(self.accomp_root)

    @unittest.skip("waiting for LP:1024041 to be fixed")
    def test_bad_accomplishment_list(self):
        # this test ensures that a bad accompishment doesn't crash the
        # daemon or get into the list

        # ensure a clean start
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        a = api.Accomplishments(None, None, True)
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
        self.assertRaises(ConfigParser.ParsingError, api.Accomplishments, None,
            None, True)
        os.remove(os.path.join(self.accomp_dir, "bad.accomplishment"))

        self.util_write_file(self.accomp_dir, "bad.accomplishment",
            "[accomplishment]\n"\
            "titlewhatever\n"\
            "description=bad desc\n")
        self.assertRaises(ConfigParser.ParsingError, api.Accomplishments, None,
            None, True)
        os.remove(os.path.join(self.accomp_dir, "bad.accomplishment"))

    # also tests get_config_value()
    def test_write_config_file_item(self):
        a = api.Accomplishments(None, None, True)
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

    # this tests the get_collection_* functions and list_collections():
    def test_get_collection_all_funcs(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        self.util_copy_accomp(self.accomp_dir, "third")
        a = api.Accomplishments(None, None, True)

        # list_collections
        collections = a.list_collections()
        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0], self.ACCOMP_SET)

        # get_collection_name
        self.assertEqual(a.get_collection_name(collections[0]),
            "Test Collection")
        self.assertRaises(KeyError, a.get_collection_name, "wrong")

        # get_collection_exists
        self.assertTrue(a.get_collection_exists(collections[0]))
        self.assertFalse(a.get_collection_exists("wrong"))
        self.assertFalse(a.get_collection_exists(""))
        self.assertFalse(a.get_collection_exists(None))

        # get_collection_authors
        authors = a.get_collection_authors(collections[0])
        # we have only 2 authors because dupes are removed
        self.assertEqual(len(authors), 2)
        for author in authors:
           self.assertTrue(author in ["Someone", "Tester <tester@tester>"])
        self.assertRaises(KeyError, a.get_collection_authors, "wrong")

        # get_collection_categories
        categories = a.get_collection_categories(collections[0])
        self.assertEqual(len(categories), 2)
        for category in categories:
           self.assertTrue(category in ["testing", "unit test"])
        self.assertRaises(KeyError, a.get_collection_categories, "wrong")

        # get_collection_data
        data = a.get_collection_data(collections[0])
        self.assertTrue(isinstance(data, dict))
        self.assertNotEquals(data['authors'], None)
        self.assertNotEquals(data['name'], None)
        self.assertNotEquals(data['categories'], None)
        self.assertRaises(KeyError, a.get_collection_data, "wrong")

    # get trophy path
    def test_get_trophy_path(self):
        self.util_remove_all_accomps(self.accomp_dir)
        self.util_copy_accomp(self.accomp_dir, "first")
        self.util_copy_accomp(self.accomp_dir, "second")
        self.util_copy_accomp(self.accomp_dir, "third")
        a = api.Accomplishments(None, None, True)

        self.assertTrue(a.get_trophy_path("%s/first" %
            self.ACCOMP_SET).endswith("first.trophy"))
        self.assertTrue(a.get_trophy_path("%s/second" %
            self.ACCOMP_SET).endswith("second.trophy"))
        self.assertTrue(a.get_trophy_path("%s/third" %
            self.ACCOMP_SET).endswith("third.trophy"))

    def test_write_extra_information_file(self):
        a = api.Accomplishments(None, None, True)

        # write extra information will make the directory for us if needed,
        # so lets remove it (if present and force it to)
        extrainfo_path = os.path.join(a.trophies_path, ".extrainformation")
        if os.path.exists(extrainfo_path):
           shutil.rmtree(extrainfo_path)

        a.write_extra_information_file("whatever", "abcdefg")
        path = os.path.join(extrainfo_path, "whatever")
        self.assertTrue(os.path.exists(path))

        # write extra info will remove a file if you don't pass in data
        a.write_extra_information_file("whatever", None)
        self.assertFalse(os.path.exists(path))

    # tests:
    # get_extra_information()
    # get_all_extra_information()
    # get_all_extra_information_required()
    def test_get_extra_information_all_funcs(self):
        a = api.Accomplishments(None, None, True)
        self.util_copy_extrainfo(self.extrainfo_dir, "info")
        self.util_copy_extrainfo(self.extrainfo_dir, "info2")
        self.util_copy_accomp(self.accomp_dir, "first")

        # get extra information
        # these won't show up until we reload
        self.assertRaises(KeyError, a.get_extra_information, self.ACCOMP_SET,
            "info")

        # should return None when the collection doesn't exist
        self.assertEqual(a.get_extra_information("wrong", "info"), None)

        # reloading should make them show up
        a.reload_accom_database()

        # will throw a KeyError if collection is right, but extrainfo is
        # wrong
        self.assertRaises(KeyError, a.get_extra_information, self.ACCOMP_SET,
            "wrong")

        ei = a.get_extra_information(self.ACCOMP_SET, "info")
        self.assertTrue(isinstance(ei, list))
        self.assertTrue(len(ei) == 1)
        self.assertEqual(ei[0]['info'], '')
        self.assertEqual(ei[0]['label'], 'Some info')
        ei = a.get_extra_information(self.ACCOMP_SET, "info2")
        self.assertTrue(isinstance(ei, list))
        self.assertTrue(len(ei) == 1)
        self.assertEqual(ei[0]['info2'], '')
        self.assertEqual(ei[0]['label'], 'More info')

        # write some data out and reload the DB
        a.write_extra_information_file("info", "whatever")
        ei = a.get_extra_information(self.ACCOMP_SET, "info")
        self.assertEqual(ei[0]['info'], 'whatever')
        a.write_extra_information_file("info2", "whatever2")
        ei = a.get_extra_information(self.ACCOMP_SET, "info2")
        self.assertEqual(ei[0]['info2'], 'whatever2')

        # get all extra information
        all_extra_info = a.get_all_extra_information()
        self.assertTrue(isinstance(all_extra_info, list))
        self.assertTrue(len(all_extra_info) == 2)
        for ei in all_extra_info:
            self.assertTrue(isinstance(ei, dict))
            self.assertEquals(ei['collection'], self.ACCOMP_SET)
            self.assertTrue(ei['description'] is not None)
            self.assertTrue(ei['example'] is not None)
            self.assertTrue(ei['needs-information'] is not None)
            self.assertTrue(ei['regex'] is '')

        # get all extra information required
        # clear out the extra info files, so everything is required
        a.write_extra_information_file("info", None)
        a.write_extra_information_file("info2", None)
        all_extra_info_required = a.get_all_extra_information_required()
        self.assertTrue(isinstance(all_extra_info, list))
        self.assertTrue(len(all_extra_info) == 2)

        # now mark fill them in with info
        a.write_extra_information_file("info", "whatever")
        a.write_extra_information_file("info2", "whatever2")
        all_extra_info_required = a.get_all_extra_information_required()
        self.assertTrue(isinstance(all_extra_info_required, list))
        self.assertTrue(len(all_extra_info_required) == 0)

if __name__ == "__main__":
    unittest.main()
