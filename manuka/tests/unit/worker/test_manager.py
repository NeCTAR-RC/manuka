#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from unittest import mock

from oslo_config import cfg

from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base
from manuka.worker import manager as worker_manager

from manuka.tests.unit.common import test_orcid_client

CONF = cfg.CONF


@mock.patch('manuka.common.clients.get_admin_keystoneclient')
@mock.patch('manuka.app.create_app')
class TestManager(base.TestCase):

    @mock.patch('manuka.models.keystone_authenticate')
    @mock.patch('manuka.worker.manager.utils')
    def test_create_user(self, mock_utils, mock_ks_auth, mock_app,
                         mock_keystone):

        swift_quota = 10
        CONF.set_override('default_quota_gb', swift_quota, 'swift')

        mock_app.return_value = self.app
        client = mock_keystone.return_value

        project = mock_utils.create_project.return_value
        project.id = 'ksp-123'
        user = mock_utils.create_user.return_value
        user.id = 'ksu-123'
        domain = mock_utils.get_domain_for_idp.return_value
        db_user, external_id = self.make_db_user()
        db_user_id = db_user.id
        self.shib_attrs['idp'] = 'fake-idp'

        token = 'token'
        mock_ks_auth.return_value = (token, project.id, user)

        manager = worker_manager.Manager()
        manager.create_user(self.shib_attrs)

        db_user = db.session.query(models.User).get(db_user_id)

        mock_utils.get_domain_for_idp.assert_called_once_with(
            self.shib_attrs['idp'])

        mock_utils.create_project.assert_called_once_with(
            client,
            "pt-%s" % db_user.id,
            "%s's project trial." % self.shib_attrs['fullname'],
            domain)

        mock_utils.create_user.assert_called_once_with(
            client,
            self.shib_attrs['mail'],
            self.shib_attrs['mail'],
            project,
            self.shib_attrs['fullname'])

        mock_utils.add_user_roles.assert_called_once_with(
            client,
            project=project,
            user=user,
            roles=['Member'])

        self.assertEqual(user.id, db_user.keystone_user_id)
        self.assertEqual('created', db_user.state)

        mock_utils.send_welcome_email.assert_called_once_with(
            user, project)

        mock_utils.add_security_groups.assert_called_once_with(
            user.id, project.id, token)
        mock_utils.set_nova_quota.assert_called_once_with(
            mock.ANY, project.id)
        mock_utils.set_swift_quota.assert_called_once_with(
            mock.ANY, project.id, swift_quota)

    @mock.patch('manuka.models.keystone_authenticate')
    @mock.patch('manuka.worker.manager.utils')
    def test_refresh_orcid(self, mock_utils,
                           mock_ks_auth, mock_app, mock_keystone):
        with mock.patch('manuka.common.orcid_client.PublicAPI',
                        new=test_orcid_client.FakePublicAPI):
            mock_app.return_value = self.app
            db_user, external_id = self.make_db_user()
            db_user_id = db_user.id

            manager = worker_manager.Manager()

            # Try with an unknown email
            manager.refresh_orcid(db_user_id, 'joe@bar.com')

            db_user = db.session.query(models.User) \
                                .filter(models.User.id == db_user_id) \
                                .one()
            # This is the value planted by 'make_db_user'
            self.assertEqual('testorchid', db_user.orcid)

            # Try with a known email
            manager.refresh_orcid(db_user_id, 'foo@bar.com')

            db_user = db.session.query(models.User) \
                                .filter(models.User.id == db_user_id) \
                                .one()
            # This is the value from the fake API
            self.assertEqual('0000-0001-0000-0001', db_user.orcid)
