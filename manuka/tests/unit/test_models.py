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


CONF = cfg.CONF


class TestModels(base.TestCase):

    def test_create_db_user(self):
        user = models.create_db_user(self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual(self.shib_attrs['id'], db_user.persistent_id)

    @freeze_time("2012-01-14")
    def test_update_db_user(self):
        # testing classic behavior: handling the mandatory attributes
        user = self.make_db_user()
        user.displayname = ''
        user.email = ''
        user.shibboleth_attributes = {}
        db.session.add(user)
        db.session.commit()
        models.update_db_user(user, self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual(self.shib_attrs["fullname"], db_user.displayname)
        self.assertEqual(self.shib_attrs["mail"], db_user.email)
        self.assertEqual(self.shib_attrs, db_user.shibboleth_attributes)
        self.assertEqual(datetime(2012, 1, 14), db_user.last_login)

    def test_update_db_user_merging(self):
        # testing classic behavior: handling the mandatory attributes
        user = self.make_db_user()
        user.displayname = ''
        user.email = ''
        user.phone_number = '460 261'
        user.mobile_number = '0401 234 567'
        user.affiliation = 'staff'
        user.orcid = 'pretty'
        user.shibboleth_attributes = {'firstname': 'George',
                                      'surname': 'Cohen',
                                      'orcid': 'ugly'}
        user.shibboleth_attributes.update(self.shib_attrs)
        self.shib_attrs.update({'firstname': ' Godfrey ',
                                'surname': 'Cohen',
                                'telephonenumber': '1800 815 270',
                                'orcid': 'ugly'})
        db.session.add(user)
        db.session.commit()
        models.update_db_user(user, self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual(self.shib_attrs["fullname"], db_user.displayname)
        self.assertEqual(self.shib_attrs["mail"], db_user.email)
        self.assertEqual(self.shib_attrs, db_user.shibboleth_attributes)
        self.assertEqual('Godfrey', db_user.first_name)
        self.assertEqual('Cohen', db_user.surname)
        self.assertEqual('1800 815 270', db_user.phone_number)
        self.assertEqual('0401 234 567', db_user.mobile_number)
        self.assertEqual('staff', db_user.affiliation)
        self.assertIsNone(db_user.home_organization)
        self.assertEqual('pretty', db_user.orcid)

    def test_update_bad_affiliation(self):
        user = self.make_db_user()
        self.shib_attrs.update({'affiliation': 'parasite'})
        db.session.add(user)
        db.session.commit()
        models.update_db_user(user, self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual('member', db_user.affiliation)
        self.assertEqual(self.shib_attrs, db_user.shibboleth_attributes)

    @mock.patch('keystoneauth1.identity.v3.Password')
    @mock.patch('manuka.models.keystone_client.Client')
    @mock.patch('manuka.common.clients.get_admin_keystoneclient')
    @mock.patch('manuka.views.worker_api.WorkerAPI')
    def test_keystone_authenticate(self, worker_api,
                                   mock_get_admin_keystone_client,
                                   mock_keystone_client,
                                   mock_keystone_password):
        mock_client = mock.Mock()
        mock_user_client = mock.Mock()
        mock_keystone_user = mock.Mock()
        mock_keystone_domain = mock.Mock()
        mock_worker_api = mock.Mock()
        worker_api.return_value = mock_worker_api
        mock_get_admin_keystone_client.return_value = mock_client
        mock_client.users.get.return_value = mock_keystone_user
        mock_client.domains.get.return_value = mock_keystone_domain
        mock_keystone_client.return_value = mock_user_client
        p1 = mock.Mock()
        p2 = mock.Mock()
        mock_user_client.projects.list.return_value = [p1, p2]
        db_user = self.make_db_user()
        db.session.add(db_user)
        db.session.commit()

        token, project_id, user = models.keystone_authenticate(db_user)

        mock_worker_api.sync_keystone_user.assert_called_once_with(
            mock.ANY, db_user.id, False)
        mock_client.users.get.assert_called_once_with(db_user.user_id)
        mock_client.domains.get.assert_called_once_with(
            mock_keystone_user.domain_id)

        mock_keystone_password.assert_called_once_with(
            username=mock_keystone_user.name,
            password=CONF.keystone.authenticate_password,
            auth_url=CONF.keystone.auth_url,
            user_domain_name=mock_keystone_domain.name,
            project_domain_name='Default'
        )

        mock_user_client.auth.client.get_token.assert_called_once_with()
        mock_user_client.projects.list.assert_called_once_with(
            user=mock_keystone_user.id)

        self.assertEqual(mock_user_client.auth.client.get_token.return_value,
                         token)
        self.assertEqual(p1.id, project_id)
        self.assertEqual(mock_keystone_user, user)
