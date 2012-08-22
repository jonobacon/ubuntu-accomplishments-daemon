"""
Tests for accomplishments daemon.
"""
import unittest
import sys
import os
import tempfile
import shutil
import subprocess
import ConfigParser
import datetime
import time
import Image
from collections import deque
from types import GeneratorType

sys.path.insert(0, os.path.join(os.path.split(__file__)[0], ".."))
from accomplishments.daemon import app, api

# These tests will modify the user's envrionment, outside of the test
# dir and so are not written/skipped:
#  - set daemon session start
#  - set block u1 notification bubbles

# These tests will require a running daemon and U1 account:
#  - get published status
#  - publish and unpublish trophies online

# Debugging:
# To debug tests, the following changes are recommended:
# 1) comment out the shutil.rmtree in tearDown()
# 2) in setUp, set self.td to a known place, like /tmp/foo (you will need
#    to create this directory as well)


class TestDaemon(unittest.TestCase):

    ACCOM_SET = "testaccom"
    LANG = "en"

    def util_copy_extrainfo(self, extrainfo_dir, extrainfo_name):
        testdir = os.path.dirname(__file__)
        src = os.path.join(testdir, "extrainformation", extrainfo_name)
        dest = os.path.join(extrainfo_dir, extrainfo_name)
        shutil.copyfile(src, dest)

    def util_copy_accom(self, accom_dir, accom_name):
        testdir = os.path.dirname(__file__)
        src = os.path.join(testdir, "accoms",
                           "%s.accomplishment" % accom_name)
        dest = os.path.join(accom_dir, "%s.accomplishment" % accom_name)
        shutil.copyfile(src, dest)

    # This function is not really needed because when tearDown runs it
    # removes the entire tree, but when debugging tests it's useful to comment
    # out the rmtree in tearDown, so then this is critical to make the tests
    # work.
    def util_remove_all_accoms(self, accom_dir):
        for f in os.listdir(accom_dir):
            os.remove(os.path.join(self.accom_dir, f))

    def util_write_about_file(self, accom_dir):
        fp = open(os.path.join(accom_dir, "ABOUT"), "w")
        fp.write("""[general]
name = Test Collection
langdefault=%s""" % self.LANG)
        fp.close()

    def util_write_config_file(self, accom_dir):
        fp = open(os.path.join(accom_dir, ".accomplishments"), "w")
        fp.write("""[config]
has_u1 = true
has_verif = 1
accompath = %s/accomplishments
trophypath = %s/accomplishments/.local/share/accomplishments/trophies
daemon_sessionstart = false
extrainfo_seen = 1""" % (self.td, self.td))
        fp.close()

    def util_write_file(self, accom_dir, name, content):
        fp = open(os.path.join(accom_dir, name), "w")
        fp.write(content)
        fp.close()

    def setUp(self):
        self.td = tempfile.mkdtemp()

        # /tmp/foo/accomplishments
        self.accoms_root = os.path.join(self.td, "accomplishments",
                                        "accomplishments")
        if not os.path.exists(self.accoms_root):
            os.makedirs(self.accoms_root)

        # /tmp/foo/accomplishments/accomplishments/.config
        self.config_dir = os.path.join(self.td, "accomplishments", ".config",
                                       "accomplishments")
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

        # /tmp/foo/accomplishments/accomplishments/testaccom
        self.accom_root = os.path.join(self.accoms_root, self.ACCOM_SET)
        if not os.path.exists(self.accom_root):
            os.makedirs(self.accom_root)

        # /tmp/foo/accomplishments/accomplishments/testaccom/en
        self.accom_dir = os.path.join(self.accom_root, self.LANG)
        if not os.path.exists(self.accom_dir):
            os.makedirs(self.accom_dir)

        # /tmp/foo/accomplishments/accomplishments/testaccom/extrainformation
        self.extrainfo_dir = os.path.join(self.accom_root, "extrainformation")
        if not os.path.exists(self.extrainfo_dir):
            os.makedirs(self.extrainfo_dir)

        # /tmp/foo/accomplishments/accomplishments/testaccom/trophyimages
        self.trophyimages_dir = os.path.join(self.accom_root, "trophyimages")
        if not os.path.exists(self.trophyimages_dir):
            os.makedirs(self.trophyimages_dir)

        # /tmp/foo/accomplishments/accomplishments/scripts
        self.scripts_root = os.path.join(self.td, "accomplishments", "scripts")
        if not os.path.exists(self.scripts_root):
            os.makedirs(self.scripts_root)

        # /tmp/foo/accomplishments/accomplishments/scripts/testaccom
        self.script_root = os.path.join(self.scripts_root, self.ACCOM_SET)
        if not os.path.exists(self.script_root):
            os.makedirs(self.script_root)

        # /tmp/foo/accomplishments/.local/share/accomplishments/trophies
        self.trophy_dir = os.path.join(self.td, "accomplishments", ".local",
                                       "share", "accomplishments", "trophies")
        if not os.path.exists(self.trophy_dir):
            os.makedirs(self.trophy_dir)

        self.util_write_about_file(self.accom_root)

        self.util_write_config_file(self.config_dir)

        os.environ['ACCOMPLISHMENTS_ROOT_DIR'] = self.td

    def tearDown(self):
        del os.environ['ACCOMPLISHMENTS_ROOT_DIR']
        shutil.rmtree(self.td)

    # also tests _load_config_file()
    def test_write_config_file(self):
        a = api.Accomplishments(None, None, True)
        config_path = os.path.join(a.dir_config, ".accomplishments")
        a._write_config_file()
        self.assertTrue(os.path.exists(config_path))
        a._load_config_file()

        # load_config will create the config file if it doesn't exist
        os.remove(config_path)
        a._load_config_file()
        self.assertTrue(os.path.exists(config_path))

    def test_create_all_trophy_icons(self):
        a = api.Accomplishments(None, None, True)
        gen_path = os.path.join(self.td,
            "accomplishments/.cache/accomplishments/trophyimages/%s"
            % self.ACCOM_SET)
        src_path = os.path.join(self.td,
            "accomplishments/accomplishments/%s/trophyimages/"
            % self.ACCOM_SET)

        testdir = os.path.dirname(__file__)
        src = os.path.join(testdir, "icons", "test.png")
        shutil.copyfile(src, os.path.join(src_path, "test.png"))

        a._create_all_trophy_icons()
        self.assertTrue(os.path.exists(gen_path))
        self.assertTrue(os.path.exists(os.path.join(gen_path, "test.png")))
        self.assertTrue(os.path.exists(os.path.join(gen_path,
            "test-locked.png")))
        self.assertTrue(os.path.exists(os.path.join(gen_path,
            "test-opportunity.png")))

    def test_create_reduced_opacity_trpohy_image(self):
        a = api.Accomplishments(None, None, True)
        path = os.path.join(self.td,
            "accomplishments/.cache/accomplishments/trophyimages/%s"
            % self.ACCOM_SET)
        testdir = os.path.dirname(__file__)
        src = os.path.join(testdir, "icons", "test.png")
        shutil.copyfile(src, os.path.join(path, "test.png"))
        im = Image.open(os.path.join(path, "test.png"))
        new_im = a._create_reduced_opacity_trophy_icon(im, 0.0)
        self.assertTrue(new_im is not None)
        new_im = a._create_reduced_opacity_trophy_icon(im, 0.01)
        self.assertTrue(new_im is not None)
        new_im = a._create_reduced_opacity_trophy_icon(im, 0.99)
        self.assertTrue(new_im is not None)

        self.assertRaises(AssertionError,
            a._create_reduced_opacity_trophy_icon, im, -1)
        self.assertRaises(AssertionError,
            a._create_reduced_opacity_trophy_icon, im, 1.01)
        self.assertRaises(AssertionError,
            a._create_reduced_opacity_trophy_icon, im, 100)

    def test_verify_ubuntu_one_account(self):
        # this just makes sure it doesn't crash, we don't know if this
        # system will have one or not
        a = api.Accomplishments(None, None, True)
        a.verify_ubuntu_one_account()

    def test_accomslist(self):
        a = api.Accomplishments(None, None, True)
        accomslist = a.accomslist()
        self.assertTrue(isinstance(accomslist, GeneratorType))
        for accom in accomslist:
            # the list should be empty so we should never hit this
            self.assertTrue(False)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        a.reload_accom_database()
        accomslist = a.accomslist()
        for accom in accomslist:
            self.assertTrue(accom in ["%s/first" % self.ACCOM_SET,
                                      "%s/second" % self.ACCOM_SET,
                                      "%s/third" % self.ACCOM_SET])

    # tests get_share_name and get_share_id
    def test_get_share_all(self):
        a = api.Accomplishments(None, None, True)
        sid = a.get_share_id()
        self.assertTrue(isinstance(sid, str))
        self.assertTrue(sid is not None)
        sid = a.get_share_id()
        self.assertTrue(isinstance(sid, str))
        self.assertTrue(sid is not None)

    def test_run_scripts(self):
        # due to LP1030208, if the daemon is running (like on a dev box)
        # it will pop off the test, but in a pbuilder or build system
        # there will be no daemon, so we can just ensure that this
        # doesn't crash
        self.util_copy_accom(self.accom_dir, "third")
        a = api.Accomplishments(None, None, True)

        # pass in None
        self.assertEqual(a.run_scripts(None), None)

        # pass in a bad arg
        self.assertEqual(a.run_scripts(122), None)

        # pass in a specific item
        self.assertEqual(a.run_scripts(["%s/third" % self.ACCOM_SET]), None)

    def test_run_script(self):
        # due to LP1030208, if the daemon is running (like on a dev box)
        # it will pop off the test, but in a pbuilder or build system
        # there will be no daemon, so we can just ensure that this
        # doesn't crash
        self.util_copy_accom(self.accom_dir, "third")
        a = api.Accomplishments(None, None, True)
        self.assertEqual(a.run_script("%s/wrong" % self.ACCOM_SET), None)
        self.assertEqual(a.run_script("wrong"), None)

        self.assertEqual(a.run_script("%s/third" % self.ACCOM_SET), None)

    def test_get_accom_date_completed(self):
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        self.util_copy_extrainfo(self.extrainfo_dir, "info")
        self.util_copy_extrainfo(self.extrainfo_dir, "info2")
        a = api.Accomplishments(None, None, True)
        a.write_extra_information_file("info", "whatever")
        a.write_extra_information_file("info2", "whatever2")

        self.assertTrue(a.accomplish("%s/first" % self.ACCOM_SET))
        self.assertTrue(a.accomplish("%s/second" % self.ACCOM_SET))
        self.assertTrue(a.accomplish("%s/third" % self.ACCOM_SET))

        trophies = a.list_trophies()
        # since "second" requires signing, it shouldn't be listed
        self.assertEqual(len(trophies), 2)

        d1 = a.get_accom_date_completed("%s/first" % self.ACCOM_SET)
        self.assertTrue(isinstance(d1, basestring))
        dt1 = datetime.datetime.strptime(d1, "%Y-%m-%d %H:%M")
        self.assertTrue(dt1 is not None)

        d3 = a.get_accom_date_completed("%s/third" % self.ACCOM_SET)
        self.assertTrue(isinstance(d3, basestring))
        dt3 = datetime.datetime.strptime(d3, "%Y-%m-%d %H:%M")
        self.assertTrue(dt3 is not None)

    def test_check_if_accom_is_locked(self):
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        self.util_copy_extrainfo(self.extrainfo_dir, "info")
        self.util_copy_extrainfo(self.extrainfo_dir, "info2")
        a = api.Accomplishments(None, None, True)
        a.write_extra_information_file("info", "whatever")
        a.write_extra_information_file("info2", "whatever2")

        self.assertFalse(a._check_if_accom_is_locked("%s/first"
                                                     % self.ACCOM_SET))
        self.assertTrue(a._check_if_accom_is_locked("%s/second"
                                                    % self.ACCOM_SET))
        self.assertFalse(a._check_if_accom_is_locked("%s/third"
                                                     % self.ACCOM_SET))
        self.assertTrue(a.accomplish("%s/first" % self.ACCOM_SET))
        self.assertFalse(a._check_if_accom_is_locked("%s/second"
                                                     % self.ACCOM_SET))

    def test_check_if_accom_is_completed(self):
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        self.util_copy_extrainfo(self.extrainfo_dir, "info")
        self.util_copy_extrainfo(self.extrainfo_dir, "info2")
        a = api.Accomplishments(None, None, True)
        a.write_extra_information_file("info", "whatever")
        a.write_extra_information_file("info2", "whatever2")

        self.assertFalse(a._check_if_accom_is_completed("%s/first"
                                                        % self.ACCOM_SET))
        self.assertFalse(a._check_if_accom_is_completed("%s/second"
                                                        % self.ACCOM_SET))
        self.assertFalse(a._check_if_accom_is_completed("%s/third"
                                                        % self.ACCOM_SET))
        self.assertTrue(a.accomplish("%s/first" % self.ACCOM_SET))
        a = api.Accomplishments(None, None, True)
        self.assertTrue(a._check_if_accom_is_completed("%s/first"
                                                       % self.ACCOM_SET))
        self.assertFalse(a._check_if_accom_is_completed("%s/second"
                                                        % self.ACCOM_SET))
        self.assertFalse(a._check_if_accom_is_completed("%s/third"
                                                        % self.ACCOM_SET))

    # this tests:
    # accomplish()
    # list_opportunities
    # list_trophies
    # list_unlocked
    # list_unlocked_not_completed
    # get_trophy_data
    def test_accomplish(self):
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        a = api.Accomplishments(None, None, True)

        # before accomplishing
        opps = a.list_opportunities()
        self.assertEqual(len(opps), 3)
        for accom in opps:
            self.assertTrue(accom in ["%s/first" % self.ACCOM_SET,
                                      "%s/second" % self.ACCOM_SET,
                                      "%s/third" % self.ACCOM_SET])

        unlocked = a.list_unlocked()
        self.assertEqual(len(unlocked), 2)
        for accom in unlocked:
            self.assertTrue(accom in ["%s/first" % self.ACCOM_SET,
                                      "%s/third" % self.ACCOM_SET])

        unlocked_nc = a.list_unlocked_not_completed()
        self.assertEqual(len(unlocked_nc), 2)
        for accom in unlocked_nc:
            self.assertTrue(accom in ["%s/first" % self.ACCOM_SET,
                                      "%s/third" % self.ACCOM_SET])

        trophies = a.list_trophies()
        self.assertEqual(len(trophies), 0)

        self.assertTrue(a.get_trophy_data("%s/first" % self.ACCOM_SET) is None)
        self.assertTrue(a.get_trophy_data("%s/second" % self.ACCOM_SET)
                        is None)
        self.assertTrue(a.get_trophy_data("%s/third" % self.ACCOM_SET) is None)

        # now let's accomplish something, it should fail without extra info
        self.assertRaises(KeyError, a.accomplish, "%s/first" % self.ACCOM_SET)

        # this time it will work
        self.util_copy_extrainfo(self.extrainfo_dir, "info")
        self.util_copy_extrainfo(self.extrainfo_dir, "info2")
        a.reload_accom_database()
        self.assertTrue(a.accomplish("%s/first" % self.ACCOM_SET))

        opps = a.list_opportunities()
        self.assertEqual(len(opps), 2)
        for accom in opps:
            self.assertTrue(accom in ["%s/second" % self.ACCOM_SET,
                                      "%s/third" % self.ACCOM_SET])

        unlocked = a.list_unlocked()
        self.assertEqual(len(unlocked), 3)
        for accom in unlocked:
            self.assertTrue(accom in ["%s/first" % self.ACCOM_SET,
                                      "%s/second" % self.ACCOM_SET,
                                      "%s/third" % self.ACCOM_SET])

        unlocked_nc = a.list_unlocked_not_completed()
        self.assertEqual(len(unlocked_nc), 2)
        for accom in unlocked_nc:
            self.assertTrue(accom in ["%s/second" % self.ACCOM_SET,
                                      "%s/third" % self.ACCOM_SET])

        trophies = a.list_trophies()
        self.assertEqual(len(trophies), 1)
        for accom in trophies:
            self.assertTrue(accom in ["%s/first" % self.ACCOM_SET])

        td = a.get_trophy_data("%s/first" % self.ACCOM_SET)
        self.assertTrue(isinstance(td, dict))

        self.assertTrue(td['date-accomplished'] is not None)
        self.assertTrue(td['version'] is not None)
        self.assertTrue(td['__name__'] == "trophy")
        self.assertTrue(td['id'] == "%s/first" % self.ACCOM_SET)
        self.assertTrue(td['needs-information'] is not None)

    def test_list_depending_on(self):
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        a = api.Accomplishments(None, None, True)

        self.assertEquals(len(a.list_depending_on("%s/first" %
                                                  self.ACCOM_SET)), 1)
        self.assertEquals(len(a.list_depending_on("%s/second" %
                                                  self.ACCOM_SET)), 0)
        self.assertEquals(len(a.list_depending_on("%s/third" %
                                                  self.ACCOM_SET)), 0)

    # tests all the get_accom_* functions, except for:
    # get_accom_icon
    # get_accom_icon_path
    # get_date_completed
    def test_get_accom_all_funcs(self):
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        a = api.Accomplishments(None, None, True)

        # get_accom_data
        data = a.get_accom_data("%s/first" % self.ACCOM_SET)
        self.assertTrue(isinstance(data, dict))
        self.assertEquals(data['title'], "My First Accomplishment")
        data = a.get_accom_data("%s/third" % self.ACCOM_SET)
        self.assertTrue(isinstance(data, dict))
        self.assertEquals(data['title'], "My Third Accomplishment")

        # get_accom_exists
        self.assertTrue(a.get_accom_exists("%s/first" % self.ACCOM_SET))
        self.assertTrue(a.get_accom_exists("%s/second" % self.ACCOM_SET))
        self.assertTrue(a.get_accom_exists("%s/third" % self.ACCOM_SET))
        self.assertFalse(a.get_accom_exists("%s/something" % self.ACCOM_SET))
        self.assertFalse(a.get_accom_exists("wrong/first"))

        # get_accom_title
        self.assertEquals(a.get_accom_title("%s/first" % self.ACCOM_SET),
                          "My First Accomplishment")
        self.assertEquals(a.get_accom_title("%s/second" % self.ACCOM_SET),
                          "My Second Accomplishment")
        self.assertEquals(a.get_accom_title("%s/third" % self.ACCOM_SET),
                          "My Third Accomplishment")
        self.assertRaises(KeyError, a.get_accom_title, "wrong")

        # get_accom_description
        self.assertTrue("example" in a.get_accom_description("%s/first" %
                                                             self.ACCOM_SET))
        self.assertTrue("example" in a.get_accom_description("%s/second" %
                                                             self.ACCOM_SET))
        self.assertTrue("example" in a.get_accom_description("%s/third" %
                                                             self.ACCOM_SET))
        self.assertRaises(KeyError, a.get_accom_description, "wrong")

        # get_accom_needs_signing
        self.assertFalse(a.get_accom_needs_signing("%s/first" % self.ACCOM_SET))
        self.assertTrue(a.get_accom_needs_signing("%s/second" % self.ACCOM_SET))
        self.assertFalse(a.get_accom_needs_signing("%s/first" % self.ACCOM_SET))
        self.assertRaises(KeyError, a.get_accom_needs_signing, "wrong")

        # get_accom_depends
        self.assertTrue(a.get_accom_depends("%s/first" % self.ACCOM_SET) == [])
        deps = a.get_accom_depends("%s/second" % self.ACCOM_SET)
        self.assertEquals(len(deps), 1)
        self.assertTrue(deps[0] == "%s/first" % self.ACCOM_SET)
        self.assertTrue(a.get_accom_depends("%s/third" % self.ACCOM_SET) == [])
        self.assertRaises(KeyError, a.get_accom_depends, "wrong")

        # get_accom_is_unlocked
        self.assertTrue(a.get_accom_is_unlocked("%s/first" % self.ACCOM_SET))
        self.assertFalse(a.get_accom_is_unlocked("%s/second" % self.ACCOM_SET))
        self.assertTrue(a.get_accom_is_unlocked("%s/third" % self.ACCOM_SET))
        self.assertRaises(KeyError, a.get_accom_is_unlocked, "wrong")

        # get_accom_is_completed
        # XXX - when we get the accomplish() code working, make some of these
        # true
        self.assertFalse(a.get_accom_is_completed("%s/first" % self.ACCOM_SET))
        self.assertFalse(a.get_accom_is_completed("%s/second" % self.ACCOM_SET))
        self.assertFalse(a.get_accom_is_completed("%s/third" % self.ACCOM_SET))
        self.assertRaises(KeyError, a.get_accom_is_completed, "wrong")

        # get_accom_script_path
        self.assertEqual(a.get_accom_script_path("%s/first" % self.ACCOM_SET),
                         None)
        self.assertEqual(a.get_accom_script_path("%s/second" % self.ACCOM_SET),
                         None)
        self.util_write_file(self.script_root, "third.py", "print 'hello'")
        sp = a.get_accom_script_path("%s/third" % self.ACCOM_SET)
        self.assertTrue(sp.endswith("third.py"))
        self.assertRaises(KeyError, a.get_accom_script_path, "wrong")

        # get_accom_needs_info
        info = a.get_accom_needs_info("%s/first" % self.ACCOM_SET)
        self.assertEqual(len(info), 2)
        for i in info:
            self.assertTrue(i in ["info", "info2"])
        self.assertEqual(a.get_accom_needs_info("%s/second" % self.ACCOM_SET),
                         [])
        self.assertEqual(a.get_accom_needs_info("%s/third" % self.ACCOM_SET),
                         [])
        self.assertRaises(KeyError, a.get_accom_needs_info, "wrong")

        # get_accom_collection
        self.assertEqual(a.get_accom_collection("%s/first" % self.ACCOM_SET),
                         self.ACCOM_SET)
        self.assertEqual(a.get_accom_collection("%s/second" % self.ACCOM_SET),
                         self.ACCOM_SET)
        self.assertEqual(a.get_accom_collection("%s/third" % self.ACCOM_SET),
                         self.ACCOM_SET)
        self.assertRaises(KeyError, a.get_accom_collection, "wrong")

        # get_accom_categories
        self.assertEqual(a.get_accom_categories("%s/first" % self.ACCOM_SET), [])
        self.assertEqual(a.get_accom_categories("%s/second" % self.ACCOM_SET),
                         [])
        categories = a.get_accom_categories("%s/third" % self.ACCOM_SET)
        self.assertEqual(len(info), 2)
        for category in categories:
            self.assertTrue(category in ["testing", "unit test"])
        self.assertRaises(KeyError, a.get_accom_categories, "wrong")

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
        self.assertTrue(mf is None)

        mf = a.get_media_file("lock.png")
        self.assertTrue(mf.endswith("lock.png"))

    def test_get_API_version(self):
        a = api.Accomplishments(None, None, True)
        version = a.get_API_version()
        self.assertTrue(isinstance(version, basestring))

    # also tests get_accom_icon_path
    def test_get_accom_icon(self):
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        a = api.Accomplishments(None, None, True)
        self.assertEquals(a.get_accom_icon('%s/first' % self.ACCOM_SET),
                          'first.jpg')
        icon_path = a.get_accom_icon_path('%s/first' % self.ACCOM_SET)
        self.assertTrue(icon_path.endswith("first-opportunity.jpg"))

        # LP 1024052 - make sure this works without a . in the filename
        self.assertEquals(a.get_accom_icon('%s/second' % self.ACCOM_SET),
                          'second')
        icon_path = a.get_accom_icon_path('%s/second' % self.ACCOM_SET)
        self.assertTrue(icon_path.endswith("second-locked"))

    def test_build_viewer_database(self):
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        a = api.Accomplishments(None, None, True)
        viewer_db = a.build_viewer_database()
        self.assertEquals(len(viewer_db), 2)

        # these match what is in the ABOUT file
        self.assertEquals(viewer_db[0]['collection-human'],
                          "Test Collection")
        self.assertEquals(viewer_db[1]['collection-human'],
                          "Test Collection")

        self.assertEquals(viewer_db[0]['collection'], "testaccom")
        self.assertEquals(viewer_db[1]['collection'], "testaccom")

        # test a few random fields
        for item in viewer_db:
            if item['title'] == "My First Accomplishment":
                self.assertTrue("opportunity" in item['iconpath'])
                self.assertTrue(item['id'] == "%s/first" % self.ACCOM_SET)
            elif item['title'] == "My Second Accomplishment":
                self.assertTrue("locked" in item['iconpath'])
                self.assertTrue(item['id'] == "%s/second" % self.ACCOM_SET)
            # this shouldn't happen
            else:
                self.assertTrue(False)

    # also tests reloading the database
    def test_list_all(self):
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")

        a = api.Accomplishments(None, None, True)
        self.assertEqual(len(a.list_accoms()), 3)

        # add a new accomp
        self.util_write_file(self.accom_dir, "fourth.accomplishment",
                             "[accomplishment]\n"
                             "title=My Fourth Accomplishment\n"
                             "description=An example accomplishment for the test suite\n")
        self.assertEqual(len(a.list_accoms()), 3)
        a.reload_accom_database()
        self.assertEqual(len(a.list_accoms()), 4)

        # remove the new accomp
        os.remove(os.path.join(self.accom_dir, "fourth.accomplishment"))
        a.reload_accom_database()
        self.assertEqual(len(a.list_accoms()), 3)

        self.util_remove_all_accoms(self.accom_dir)

    def test_missing_about_file(self):
        os.remove(os.path.join(self.accom_root, "ABOUT"))
        self.assertRaises(LookupError, api.Accomplishments, None, None, True)

        # put the file back
        self.util_write_about_file(self.accom_root)

    def test_bad_accomplishment_list(self):
        # this test ensures that a bad accompishment doesn't crash the
        # daemon or get into the list

        # ensure a clean start
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        a = api.Accomplishments(None, None, True)
        self.assertEqual(len(a.list_accoms()), 1)
        self.util_write_file(self.accom_dir, "bad.accomplishment",
                             "[accomplishment]\n"
                             "descriptionbad desc\n")
        a.reload_accom_database()
        self.assertEqual(len(a.list_accoms()), 1)

        self.util_write_file(self.accom_dir, "bad.accomplishment",
                             "descriptionbad desc\n")
        a.reload_accom_database()
        self.assertEqual(len(a.list_accoms()), 1)

        # cleanup
        self.util_remove_all_accoms(self.accom_dir)

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
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        a = api.Accomplishments(None, None, True)

        # list_collections
        collections = a.list_collections()
        self.assertEqual(len(collections), 1)
        self.assertEqual(collections[0], self.ACCOM_SET)

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
        self.util_remove_all_accoms(self.accom_dir)
        self.util_copy_accom(self.accom_dir, "first")
        self.util_copy_accom(self.accom_dir, "second")
        self.util_copy_accom(self.accom_dir, "third")
        a = api.Accomplishments(None, None, True)

        self.assertTrue(a.get_trophy_path("%s/first" %
                                          self.ACCOM_SET).endswith("first.trophy"))
        self.assertTrue(a.get_trophy_path("%s/second" %
                                          self.ACCOM_SET).endswith("second.trophy"))
        self.assertTrue(a.get_trophy_path("%s/third" %
                                          self.ACCOM_SET).endswith("third.trophy"))

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

    @unittest.skip("won't work on the build server, under investigation")
    def test_get_is_asc_correct(self):
        a = api.Accomplishments(None, None, True)

        testdir = os.path.dirname(__file__)
        a_src = os.path.join(testdir, "trophies", "good.trophy.asc")
        a_dest = os.path.join(self.td, "good.trophy.asc")
        shutil.copyfile(a_src, a_dest)
        t_src = os.path.join(testdir, "trophies", "good.trophy")
        t_dest = os.path.join(self.td, "good.trophy")
        shutil.copyfile(t_src, t_dest)
        self.assertTrue(a._get_is_asc_correct(a_dest))

        testdir = os.path.dirname(__file__)
        a_src = os.path.join(testdir, "trophies", "bad.trophy.asc")
        a_dest = os.path.join(self.td, "bad.trophy.asc")
        shutil.copyfile(a_src, a_dest)
        t_src = os.path.join(testdir, "trophies", "bad.trophy")
        t_dest = os.path.join(self.td, "bad.trophy")
        shutil.copyfile(t_src, t_dest)
        self.assertFalse(a._get_is_asc_correct(a_dest))

        # bad path should return false, not an exception
        self.assertFalse(a._get_is_asc_correct("abcdefg"))

    def test_create_extra_information_file(self):
        a = api.Accomplishments(None, None, True)

        # write extra information will make the directory for us if needed,
        # so lets remove it (if present and force it to)
        extrainfo_path = os.path.join(a.trophies_path, ".extrainformation")
        if os.path.exists(extrainfo_path):
            shutil.rmtree(extrainfo_path)

        a.create_extra_information_file("whatever", "abcdefg")
        path = os.path.join(extrainfo_path, "whatever")
        self.assertTrue(os.path.exists(path))
        statinfo = os.stat(path)

        # create extra info will refuse to overwrite an existing file
        time.sleep(1)
        a.create_extra_information_file("whatever", "123456")
        statinfo_after = os.stat(path)
        self.assertTrue(statinfo_after.st_ctime == statinfo.st_ctime)

    # tests:
    # get_extra_information()
    # get_all_extra_information()
    # get_all_extra_information_required()
    def test_get_extra_information_all_funcs(self):
        a = api.Accomplishments(None, None, True)
        self.util_copy_extrainfo(self.extrainfo_dir, "info")
        self.util_copy_extrainfo(self.extrainfo_dir, "info2")
        self.util_copy_accom(self.accom_dir, "first")

        # get extra information
        # these won't show up until we reload
        self.assertRaises(KeyError, a.get_extra_information, self.ACCOM_SET,
                          "info")

        # should return None when the collection doesn't exist
        self.assertEqual(a.get_extra_information("wrong", "info"), None)

        # reloading should make them show up
        a.reload_accom_database()

        # will throw a KeyError if collection is right, but extrainfo is
        # wrong
        self.assertRaises(KeyError, a.get_extra_information, self.ACCOM_SET,
                          "wrong")

        ei = a.get_extra_information(self.ACCOM_SET, "info")
        self.assertTrue(isinstance(ei, list))
        self.assertTrue(len(ei) == 1)
        self.assertEqual(ei[0]['info'], '')
        self.assertEqual(ei[0]['label'], 'Some info')
        ei = a.get_extra_information(self.ACCOM_SET, "info2")
        self.assertTrue(isinstance(ei, list))
        self.assertTrue(len(ei) == 1)
        self.assertEqual(ei[0]['info2'], '')
        self.assertEqual(ei[0]['label'], 'More info')

        # write some data out
        a.write_extra_information_file("info", "whatever")
        ei = a.get_extra_information(self.ACCOM_SET, "info")
        self.assertEqual(ei[0]['info'], 'whatever')
        a.write_extra_information_file("info2", "whatever2")
        ei = a.get_extra_information(self.ACCOM_SET, "info2")
        self.assertEqual(ei[0]['info2'], 'whatever2')

        # get all extra information
        all_extra_info = a.get_all_extra_information()
        self.assertTrue(isinstance(all_extra_info, list))
        self.assertTrue(len(all_extra_info) == 2)
        for ei in all_extra_info:
            self.assertTrue(isinstance(ei, dict))
            self.assertEquals(ei['collection'], self.ACCOM_SET)
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
