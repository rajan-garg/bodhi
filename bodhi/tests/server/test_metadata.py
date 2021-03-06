# -*- coding: utf-8 -*-
# Copyright 2007-2018 Red Hat, Inc. and others.
#
# This file is part of Bodhi.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.

from datetime import datetime
from hashlib import sha256
from os.path import join, exists, basename
import glob
import os
import shutil
import tempfile

import createrepo_c
import mock

from bodhi.server.buildsys import (setup_buildsystem, teardown_buildsystem,
                                   DevBuildsys)
from bodhi.server.config import config
from bodhi.server.models import Release, Update, UpdateRequest, UpdateStatus
from bodhi.server.metadata import UpdateInfoMetadata
from bodhi.server.util import mkmetadatadir
from bodhi.tests.server import base, create_update


class UpdateInfoMetadataTestCase(base.BaseTestCase):
    def setUp(self):
        """
        Initialize our temporary repo.
        """
        super(UpdateInfoMetadataTestCase, self).setUp()
        setup_buildsystem({'buildsystem': 'dev'})
        self.tempdir = tempfile.mkdtemp('bodhi')
        self.tempcompdir = join(self.tempdir, 'f17-updates-testing')
        self.temprepo = join(self.tempcompdir, 'compose', 'Everything', 'i386', 'os')
        mkmetadatadir(join(self.temprepo, 'f17-updates-testing', 'i386'))
        config['cache_dir'] = os.path.join(self.tempdir, 'cache')
        os.makedirs(config['cache_dir'])

    def tearDown(self):
        """
        Clean up the tempdir.
        """
        super(UpdateInfoMetadataTestCase, self).tearDown()
        teardown_buildsystem()
        shutil.rmtree(self.tempdir)
        config['cache_dir'] = None


class TestAddUpdate(UpdateInfoMetadataTestCase):
    """
    This class contains tests for the UpdateInfoMetadata.add_update() method.
    """

    def test_build_not_in_builds(self):
        """
        Test correct behavior when a build in update.builds isn't found in self.builds() and
        koji.getBuild() is called instead.
        """
        update = self.db.query(Update).one()
        now = datetime(year=2018, month=2, day=8, hour=12, minute=41, second=4)
        update.date_pushed = now
        update.date_modified = now
        md = UpdateInfoMetadata(update.release, update.request, self.db, self.temprepo,
                                close_shelf=False)

        md.add_update(update)

        md.shelf.close()

        self.assertEqual(len(md.uinfo.updates), 1)
        self.assertEquals(md.uinfo.updates[0].title, update.title)
        self.assertEquals(md.uinfo.updates[0].release, update.release.long_name)
        self.assertEquals(md.uinfo.updates[0].status, update.status.value)
        self.assertEquals(md.uinfo.updates[0].updated_date, update.date_modified)
        self.assertEquals(md.uinfo.updates[0].fromstr, config.get('bodhi_email'))
        self.assertEquals(md.uinfo.updates[0].rights, config.get('updateinfo_rights'))
        self.assertEquals(md.uinfo.updates[0].description, update.notes)
        self.assertEquals(md.uinfo.updates[0].id, update.alias)
        self.assertEquals(md.uinfo.updates[0].severity, 'Moderate')
        self.assertEqual(len(md.uinfo.updates[0].references), 2)
        bug = md.uinfo.updates[0].references[0]
        self.assertEquals(bug.href, update.bugs[0].url)
        self.assertEquals(bug.id, '12345')
        self.assertEquals(bug.type, 'bugzilla')
        cve = md.uinfo.updates[0].references[1]
        self.assertEquals(cve.type, 'cve')
        self.assertEquals(cve.href, update.cves[0].url)
        self.assertEquals(cve.id, update.cves[0].cve_id)
        self.assertEqual(len(md.uinfo.updates[0].collections), 1)
        col = md.uinfo.updates[0].collections[0]
        self.assertEquals(col.name, update.release.long_name)
        self.assertEquals(col.shortname, update.release.name)
        self.assertEqual(len(col.packages), 2)
        pkg = col.packages[0]
        self.assertEquals(pkg.epoch, '0')
        # It's a little goofy, but the DevBuildsys is going to return TurboGears rpms when its
        # listBuildRPMs() method is called, so let's just roll with it.
        self.assertEquals(pkg.name, 'TurboGears')
        self.assertEquals(
            pkg.src,
            ('https://download.fedoraproject.org/pub/fedora/linux/updates/17/SRPMS/T/'
             'TurboGears-1.0.2.2-2.fc17.src.rpm'))
        self.assertEquals(pkg.version, '1.0.2.2')
        self.assertFalse(pkg.reboot_suggested)
        self.assertEquals(pkg.arch, 'src')
        self.assertEquals(pkg.filename, 'TurboGears-1.0.2.2-2.fc17.src.rpm')
        pkg = col.packages[1]
        self.assertEquals(pkg.epoch, '0')
        self.assertEquals(pkg.name, 'TurboGears')
        self.assertEquals(
            pkg.src,
            ('https://download.fedoraproject.org/pub/fedora/linux/updates/17/i386/T/'
             'TurboGears-1.0.2.2-2.fc17.noarch.rpm'))
        self.assertEquals(pkg.version, '1.0.2.2')
        self.assertFalse(pkg.reboot_suggested)
        self.assertEquals(pkg.arch, 'noarch')
        self.assertEquals(pkg.filename, 'TurboGears-1.0.2.2-2.fc17.noarch.rpm')

    def test_date_modified_none(self):
        """The metadata should use utcnow() if an update's date_modified is None."""
        update = self.db.query(Update).one()
        update.date_modified = None
        md = UpdateInfoMetadata(update.release, update.request, self.db, self.temprepo,
                                close_shelf=False)

        md.add_update(update)

        md.shelf.close()
        self.assertEqual(len(md.uinfo.updates), 1)
        self.assertTrue(abs((datetime.utcnow() - md.uinfo.updates[0].updated_date).seconds) < 2)

    def test_date_pushed_none(self):
        """The metadata should use utcnow() if an update's date_pushed is None."""
        update = self.db.query(Update).one()
        update.date_pushed = None
        md = UpdateInfoMetadata(update.release, update.request, self.db, self.temprepo,
                                close_shelf=False)

        md.add_update(update)

        md.shelf.close()
        self.assertEqual(len(md.uinfo.updates), 1)
        self.assertTrue(abs((datetime.utcnow() - md.uinfo.updates[0].issued_date).seconds) < 2)

    def test_rpm_with_arch(self):
        """Ensure that an RPM with a non 386 arch gets handled correctly."""
        update = self.db.query(Update).one()
        md = UpdateInfoMetadata(update.release, update.request, self.db, self.temprepo,
                                close_shelf=False)
        # Set the arch to aarch64
        fake_rpms = [{
            'nvr': 'TurboGears-1.0.2.2-2.fc17', 'buildtime': 1178868422, 'arch': 'aarch64',
            'id': 62330, 'size': 761742, 'build_id': 6475, 'name': 'TurboGears', 'epoch': None,
            'version': '1.0.2.2', 'release': '2.fc17', 'buildroot_id': 1883,
            'payloadhash': '6787febe92434a9be2a8f309d0e2014e'}]

        with mock.patch.object(md, 'get_rpms', mock.MagicMock(return_value=fake_rpms)):
            md.add_update(update)

        md.shelf.close()
        col = md.uinfo.updates[0].collections[0]
        self.assertEqual(len(col.packages), 1)
        pkg = col.packages[0]
        self.assertEquals(
            pkg.src,
            ('https://download.fedoraproject.org/pub/fedora/linux/updates/17/aarch64/T/'
             'TurboGears-1.0.2.2-2.fc17.aarch64.rpm'))

    def test_rpm_with_epoch(self):
        """Ensure that an RPM with an Epoch gets handled correctly."""
        update = self.db.query(Update).one()
        md = UpdateInfoMetadata(update.release, update.request, self.db, self.temprepo,
                                close_shelf=False)
        # We'll fake the return of get_rpms so we can inject an epoch of 42.
        fake_rpms = [{
            'nvr': 'TurboGears-1.0.2.2-2.fc17', 'buildtime': 1178868422, 'arch': 'src', 'id': 62330,
            'size': 761742, 'build_id': 6475, 'name': 'TurboGears', 'epoch': 42,
            'version': '1.0.2.2', 'release': '2.fc17', 'buildroot_id': 1883,
            'payloadhash': '6787febe92434a9be2a8f309d0e2014e'}]

        with mock.patch.object(md, 'get_rpms', mock.MagicMock(return_value=fake_rpms)):
            md.add_update(update)

        md.shelf.close()
        col = md.uinfo.updates[0].collections[0]
        self.assertEqual(len(col.packages), 1)
        pkg = col.packages[0]
        self.assertEquals(pkg.epoch, '42')


class TestFetchUpdates(UpdateInfoMetadataTestCase):
    """Test the UpdateInfoMetadata._fetch_updates() method."""

    @mock.patch('bodhi.server.metadata.log.warn')
    def test_build_unassociated(self, warn):
        """A warning should be logged if the Bodhi Build object is not associated with an Update."""
        update = self.db.query(Update).one()
        update.date_pushed = None
        u = create_update(self.db, [u'TurboGears-1.0.2.2-4.fc17'])
        u.builds[0].update = None
        self.db.flush()

        # _fetch_updates() is called as part of UpdateInfoMetadata.__init__() so we'll just
        # instantiate one.
        md = UpdateInfoMetadata(update.release, update.request, self.db, self.temprepo,
                                close_shelf=False)

        warn.assert_called_once_with(
            'TurboGears-1.0.2.2-4.fc17 does not have a corresponding update')
        # Since the Build didn't have an Update, no Update should have been added to md.updates.
        self.assertEqual(md.updates, set([]))


class TestUpdateInfoMetadata(UpdateInfoMetadataTestCase):

    def setUp(self):
        super(TestUpdateInfoMetadata, self).setUp()

        self._new_mash_stage_dir = tempfile.mkdtemp()
        self._mash_stage_dir = config['mash_stage_dir']
        self._mash_dir = config['mash_dir']
        config['mash_stage_dir'] = self._new_mash_stage_dir
        config['mash_dir'] = os.path.join(config['mash_stage_dir'], 'mash')
        config['cache_dir'] = os.path.join(config['mash_stage_dir'], 'cache')
        os.makedirs(config['cache_dir'])
        os.makedirs(os.path.join(config['mash_dir'], 'f17-updates-testing'))

        # Initialize our temporary repo
        mkmetadatadir(self.temprepo)
        mkmetadatadir(join(self.tempcompdir, 'compose', 'Everything', 'source', 'tree'))
        self.repodata = join(self.temprepo, 'repodata')
        assert exists(join(self.repodata, 'repomd.xml'))

        DevBuildsys.__rpms__ = [{
            'arch': 'src',
            'build_id': 6475,
            'buildroot_id': 1883,
            'buildtime': 1178868422,
            'epoch': None,
            'id': 62330,
            'name': 'bodhi',
            'nvr': 'bodhi-2.0-1.fc17',
            'release': '1.fc17',
            'size': 761742,
            'version': '2.0'
        }]

    def tearDown(self):
        shutil.rmtree(self.tempdir)
        config['mash_stage_dir'] = self._mash_stage_dir
        config['mash_dir'] = self._mash_dir
        config['cache_dir'] = None
        shutil.rmtree(self._new_mash_stage_dir)
        super(TestUpdateInfoMetadata, self).setUp()

    def _verify_updateinfo(self, repodata):
        updateinfos = glob.glob(join(repodata, "*-updateinfo.xml*"))
        assert len(updateinfos) == 1, "We generated %d updateinfo metadata" % len(updateinfos)
        updateinfo = updateinfos[0]
        hash = basename(updateinfo).split("-", 1)[0]
        hashed = sha256(open(updateinfo).read()).hexdigest()
        assert hash == hashed, "File: %s\nHash: %s" % (basename(updateinfo), hashed)
        return updateinfo

    def get_notice(self, uinfo, title):
        for record in uinfo.updates:
            if record.title == title:
                return record

    def test___init___uses_bz2_for_epel(self):
        """Assert that the __init__() method sets the comp_type attribute to cr.BZ2 for EPEL."""
        epel_7 = Release(id_prefix="FEDORA-EPEL", stable_tag='epel7')

        md = UpdateInfoMetadata(epel_7, UpdateRequest.stable, self.db, self.tempdir)

        self.assertEqual(md.comp_type, createrepo_c.BZ2)

    def test___init___uses_xz_for_fedore(self):
        """Assert that the __init__() method sets the comp_type attribute to cr.XZ for Fedora."""
        fedora = Release.query.one()

        md = UpdateInfoMetadata(fedora, UpdateRequest.stable, self.db, self.tempdir)

        self.assertEqual(md.comp_type, createrepo_c.XZ)

    def test_extended_metadata(self):
        self._test_extended_metadata(True)

    def test_extended_metadata_no_alias(self):
        self._test_extended_metadata(False)

    def test_extended_metadata_cache(self):
        """Asserts that when the same update is retrieved twice, the info is unshelved.

        After the first run, we clear the buildsystem.__rpms__ so that there would be no way to
        again retrieve the info from the buildsystem, and it'll have to be returned from the
        cache.
        """
        self._test_extended_metadata(True)
        shutil.rmtree(self.temprepo)
        mkmetadatadir(self.temprepo)
        mkmetadatadir(join(self.tempcompdir, 'compose', 'Everything', 'source', 'tree'))
        DevBuildsys.__rpms__ = []
        self._test_extended_metadata(True)

    def _test_extended_metadata(self, has_alias):
        update = self.db.query(Update).one()

        # Pretend it's pushed to testing
        update.status = UpdateStatus.testing
        update.request = None
        if not has_alias:
            update.alias = None
        update.date_pushed = datetime.utcnow()
        DevBuildsys.__tagged__[update.title] = ['f17-updates-testing']

        # Generate the XML
        md = UpdateInfoMetadata(update.release, update.request, self.db, self.tempcompdir)

        # Insert the updateinfo.xml into the repository
        md.insert_updateinfo(self.tempcompdir)
        updateinfo = self._verify_updateinfo(self.repodata)

        # Read an verify the updateinfo.xml.gz
        uinfo = createrepo_c.UpdateInfo(updateinfo)
        notice = self.get_notice(uinfo, 'mutt-1.5.14-1.fc13')
        self.assertIsNone(notice)

        self.assertEquals(len(uinfo.updates), 1)
        notice = uinfo.updates[0]

        self.assertIsNotNone(notice)
        self.assertEquals(notice.title, update.title)
        self.assertEquals(notice.release, update.release.long_name)
        self.assertEquals(notice.status, update.status.value)
        if update.date_modified:
            self.assertEquals(notice.updated_date, update.date_modified)
        self.assertEquals(notice.fromstr, config.get('bodhi_email'))
        self.assertEquals(notice.rights, config.get('updateinfo_rights'))
        self.assertEquals(notice.description, update.notes)
        self.assertEquals(notice.id, update.alias)
        self.assertEquals(notice.severity, 'Moderate')
        bug = notice.references[0]
        self.assertEquals(bug.href, update.bugs[0].url)
        self.assertEquals(bug.id, '12345')
        self.assertEquals(bug.type, 'bugzilla')
        cve = notice.references[1]
        self.assertEquals(cve.type, 'cve')
        self.assertEquals(cve.href, update.cves[0].url)
        self.assertEquals(cve.id, update.cves[0].cve_id)

        col = notice.collections[0]
        self.assertEquals(col.name, update.release.long_name)
        self.assertEquals(col.shortname, update.release.name)

        pkg = col.packages[0]
        self.assertEquals(pkg.epoch, '0')
        self.assertEquals(pkg.name, 'TurboGears')
        self.assertEquals(
            pkg.src,
            ('https://download.fedoraproject.org/pub/fedora/linux/updates/testing/17/SRPMS/T/'
             'TurboGears-1.0.2.2-2.fc17.src.rpm'))
        self.assertEquals(pkg.version, '1.0.2.2')
        self.assertFalse(pkg.reboot_suggested)
        self.assertEquals(pkg.arch, 'src')
        self.assertEquals(pkg.filename, 'TurboGears-1.0.2.2-2.fc17.src.rpm')
