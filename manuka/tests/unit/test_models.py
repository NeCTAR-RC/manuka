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

from datetime import datetime
from unittest import mock

from freezegun import freeze_time
from oslo_config import cfg

from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base
from manuka.tests.unit import fake_shib


CONF = cfg.CONF


class TestModels(base.TestCase):

    def test_create_db_user(self):
        user, external_id = models.create_db_user(self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        external_ids = db.session.query(models.ExternalId).filter_by(
            user_id=user.id).all()
        self.assertEqual(1, len(external_ids))
        self.assertEqual(fake_shib.ID, external_ids[0].persistent_id)
        self.assertEqual(fake_shib.IDP, external_ids[0].idp)
        self.assertEqual(external_ids[0].user, db_user)
        self.assertEqual('new', db_user.state)

    @freeze_time("2012-01-14")
    def test_update_db_user(self):
        # testing classic behavior: handling the mandatory attributes
        user = self.make_db_user()
        external_id = user.external_ids[0]
        user.displayname = ''
        user.email = ''
        external_id.attributes = {}
        db.session.add(external_id)
        db.session.add(user)
        db.session.commit()
        models.update_db_user(user, external_id, self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual(self.shib_attrs["fullname"], db_user.displayname)
        self.assertEqual(self.shib_attrs["mail"], db_user.email)
        self.assertEqual(self.shib_attrs, db_user.external_ids[0].attributes)
        self.assertEqual(datetime(2012, 1, 14), db_user.last_login)

    def test_update_db_user_merging(self):
        # testing classic behavior: handling the mandatory attributes
        user = self.make_db_user()
        external_id = user.external_ids[0]
        user.displayname = ''
        user.email = ''
        user.phone_number = '460 261'
        user.mobile_number = '0401 234 567'
        user.affiliation = 'staff'
        user.orcid = 'pretty'
        external_id.attributes = {'firstname': 'George',
                                  'surname': 'Cohen',
                                  'orcid': 'ugly'}
        external_id.attributes.update(self.shib_attrs)
        self.shib_attrs.update({'firstname': ' Godfrey ',
                                'surname': 'Cohen',
                                'telephonenumber': '1800 815 270',
                                'orcid': 'ugly'})
        db.session.add(user)
        db.session.add(external_id)
        db.session.commit()

        models.update_db_user(user, external_id, self.shib_attrs)

        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual(self.shib_attrs["fullname"], db_user.displayname)
        self.assertEqual(self.shib_attrs["mail"], db_user.email)
        self.assertEqual(self.shib_attrs, db_user.external_ids[0].attributes)
        self.assertEqual('Godfrey', db_user.first_name)
        self.assertEqual('Cohen', db_user.surname)
        self.assertEqual('1800 815 270', db_user.phone_number)
        self.assertEqual('0401 234 567', db_user.mobile_number)
        self.assertEqual('staff', db_user.affiliation)
        self.assertIsNone(db_user.home_organization)
        self.assertEqual('pretty', db_user.orcid)

    def test_update_bad_affiliation(self):
        user = self.make_db_user()
        external_id = user.external_ids[0]
        self.shib_attrs.update({'affiliation': 'parasite'})
        models.update_db_user(user, external_id, self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual('member', db_user.affiliation)
        self.assertEqual(self.shib_attrs, db_user.external_ids[0].attributes)

    @mock.patch('keystoneauth1.identity.v3.Password')
    @mock.patch('manuka.models.keystone_client.Client')
    @mock.patch('manuka.common.clients.get_admin_keystoneclient')
    @mock.patch('manuka.models.sync_keystone_user')
    def test_keystone_authenticate(self, mock_sync_keystone_user,
                                   mock_get_admin_keystone_client,
                                   mock_keystone_client,
                                   mock_keystone_password):

        client = mock_get_admin_keystone_client.return_value
        keystone_user = client.users.get.return_value
        keystone_domain = client.domains.get.return_value
        user_client = mock_keystone_client.return_value
        updated_keystone_user = mock_sync_keystone_user.return_value
        p1 = mock.Mock()
        p2 = mock.Mock()
        user_client.projects.list.return_value = [p1, p2]
        db_user = self.make_db_user()

        token, project_id, user = models.keystone_authenticate(db_user)

        mock_sync_keystone_user.assert_called_once_with(
            client, db_user, keystone_user, False)
        client.users.get.assert_called_once_with(db_user.keystone_user_id)
        client.domains.get.assert_called_once_with(
            keystone_user.domain_id)

        mock_keystone_password.assert_called_once_with(
            username=updated_keystone_user.name,
            password=CONF.keystone.authenticate_password,
            auth_url=CONF.keystone.auth_url,
            user_domain_name=keystone_domain.name,
            project_domain_name='Default'
        )

        user_client.auth.client.get_token.assert_called_once_with()
        user_client.projects.list.assert_called_once_with(
            user=updated_keystone_user.id)

        self.assertEqual(user_client.auth.client.get_token.return_value,
                         token)
        self.assertEqual(p1.id, project_id)
        self.assertEqual(updated_keystone_user, user)

    @mock.patch('manuka.common.clients.get_admin_keystoneclient')
    def test_sync_keystone_user(self, mock_keystone):
        keystone_user = mock.Mock(email='email1', full_name='name1')
        mock_client = mock_keystone.return_value
        mock_client.users.get.return_value = keystone_user

        db_user = self.make_db_user(email='email1')

        updated_keystone_user = models.sync_keystone_user(mock_client, db_user,
                                                          keystone_user)

        mock_client.users.update.assert_called_once_with(
            keystone_user.id, full_name=db_user.displayname)
        self.assertEqual(mock_client.users.update.return_value,
                         updated_keystone_user)

    @mock.patch('manuka.common.clients.get_admin_keystoneclient')
    def test_sync_keystone_user_sync_username(self, mock_keystone):
        keystone_user = mock.Mock(email='email1', full_name='name1')
        keystone_user.name = 'oldname'
        mock_client = mock_keystone.return_value
        mock_client.users.get.return_value = keystone_user

        db_user = self.make_db_user(email='email1')

        updated_keystone_user = models.sync_keystone_user(
            mock_client, db_user, keystone_user, set_username_as_email=True)

        mock_client.users.update.assert_called_once_with(
            keystone_user.id, full_name=db_user.displayname,
            name='email1')
        self.assertEqual(mock_client.users.update.return_value,
                         updated_keystone_user)
