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

from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base


class TestUserApiBase(base.ApiTestCase):

    def setUp(self):
        super().setUp()
        user, external_id = self.make_db_user(state='new', agreed_terms=False,
                                              email='test@example.com')
        self.user = user


class TestUserApi(TestUserApiBase):

    def test_user_list(self):
        response = self.client.get('/api/v1/users/')

        self.assert200(response)
        results = response.get_json().get('results')
        self.assertEqual(1, len(results))
        self.assertUserEqual(self.user, results[0])

    def test_user_get(self):
        response = self.client.get('/api/v1/users/%s/' %
                                   self.user.keystone_user_id)

        self.assert200(response)
        self.assertUserEqual(self.user, response.get_json())

    def test_user_update(self):
        new_orcid = 'new-orcid'
        data = {'orcid': new_orcid}
        response = self.client.patch('/api/v1/users/%s/' %
                                     self.user.keystone_user_id,
                                     json=data)

        self.assert200(response)

        db_user = db.session.query(models.User).get(self.user.id)
        self.assertUserEqual(db_user, response.get_json())

    def _test_user_update_invalid(self, status):
        new_id = '2333'
        data = {'id': new_id}
        response = self.client.patch('/api/v1/users/%s/' %
                                     self.user.keystone_user_id,
                                     json=data)

        self.assertStatus(response, status)

    def test_user_update_invalid(self):
        self._test_user_update_invalid(401)

    def _test_user_search(self, query, expected_results):
        data = {'search': query}
        response = self.client.post('/api/v1/users/search/', data=data)
        results = response.get_json().get('results')

        self.assert200(response)
        self.assertEqual(len(expected_results), len(results))
        if len(expected_results) == 1:
            self.assertUserEqual(expected_results[0], results[0])

    def test_user_search(self):
        user1, external_id = self.make_db_user(
            id=1, displayname='displayname1', email='search1@example.com')
        user2, external_id = self.make_db_user(
            id=2, displayname='displayname2', email='search2@example.com')
        user3, external_id = self.make_db_user(
            id=3, displayname='other3', email='search3@example.com')

        self._test_user_search('displayname1', [user1])
        self._test_user_search('search1', [user1])
        self._test_user_search('displayname2', [user2])
        self._test_user_search('search2', [user2])
        self._test_user_search('displayname', [user1, user2])
        self._test_user_search('search', [user1, user2, user3])

    def test_user_search_small_query(self):
        data = {'search': 'ab'}
        response = self.client.post('/api/v1/users/search/', data=data)
        self.assert400(response)

    def test_user_delete(self):
        response = self.client.delete('/api/v1/users/%s/' %
                                      self.user.id)
        self.assert405(response)

    def test_orcid_refresh(self):
        with mock.patch('manuka.worker.utils.refresh_orcid') as mock_refresh:
            mock_refresh.return_value = True
            response = self.client.post('/api/v1/users/%s/refresh-orcid/' %
                                        self.user.keystone_user_id)
            self.assert200(response)

    def test_orcid_refresh_failed(self):
        with mock.patch('manuka.worker.utils.refresh_orcid') as mock_refresh:
            mock_refresh.return_value = False
            response = self.client.post('/api/v1/users/%s/refresh-orcid/' %
                                        self.user.keystone_user_id)
            self.assert500(response)


class TestUserApiUser(TestUserApi):

    ROLES = ['member']

    def setUp(self):
        super().setUp()
        user_self, external_id = self.make_db_user(
            state='new', agreed_terms=False, email='test@example.com',
            id=base.USER_ID)
        self.user_self = user_self

    def test_user_list(self):
        response = self.client.get('/api/v1/users/')
        self.assert403(response)

    def test_user_get(self):
        response = self.client.get('/api/v1/users/%s/' %
                                   self.user.keystone_user_id)
        self.assert404(response)

    def test_user_update(self):
        new_orcid = 'new-orcid'
        data = {'orcid': new_orcid}
        response = self.client.patch('/api/v1/users/%s/' %
                                     self.user.keystone_user_id,
                                     json=data)
        self.assert404(response)

    def test_user_get_self(self):
        response = self.client.get('/api/v1/users/%s/' % base.KEYSTONE_USER_ID)

        self.assert200(response)
        self.assertUserEqual(self.user_self, response.get_json())

    def test_user_update_self(self):
        new_orcid = 'new-orcid'
        data = {'orcid': new_orcid}
        response = self.client.patch('/api/v1/users/%s/' %
                                     base.KEYSTONE_USER_ID,
                                     json=data)
        self.assert200(response)

        db_user = db.session.query(models.User).get(base.USER_ID)
        self.assertUserEqual(db_user, response.get_json())

    def test_user_update_invalid(self):
        self._test_user_update_invalid(404)

    def test_user_search(self):
        data = {'search': 'needle'}
        response = self.client.post('/api/v1/users/search/', data=data)
        self.assert403(response)

    def test_user_search_small_query(self):
        data = {'search': 'ab'}
        response = self.client.post('/api/v1/users/search/', data=data)
        self.assert403(response)

    def test_orcid_refresh(self):
        with mock.patch('manuka.worker.utils.refresh_orcid') as mock_refresh:
            mock_refresh.return_value = True
            response = self.client.post('/api/v1/users/%s/refresh-orcid/' %
                                        self.user.keystone_user_id)
            self.assert404(response)

    def test_orcid_refresh_failed(self):
        with mock.patch('manuka.worker.utils.refresh_orcid') as mock_refresh:
            mock_refresh.return_value = False
            response = self.client.post('/api/v1/users/%s/refresh-orcid/' %
                                        self.user.keystone_user_id)
            self.assert404(response)

    def test_orcid_refresh_self(self):
        with mock.patch('manuka.worker.utils.refresh_orcid') as mock_refresh:
            mock_refresh.return_value = True
            response = self.client.post('/api/v1/users/%s/refresh-orcid/' %
                                        self.user_self.keystone_user_id)
            self.assert200(response)


class PendingTestUserApi(base.ApiTestCase):

    def setUp(self):
        super().setUp()
        user, external_id = self.make_db_user(
            state='registered', agreed_terms=True, email='test@example.com',
            keystone_user_id=None)
        self.user = user

    def assertUserEqual(self, user, api_user):
        return super().assertUserEqual(user, api_user, keystone_id_as_id=False)

    def test_user_list(self):
        response = self.client.get('/api/v1/pending-users/')

        self.assert200(response)
        results = response.get_json().get('results')
        self.assertEqual(1, len(results))
        self.assertUserEqual(self.user, results[0])

    def test_user_get(self):
        response = self.client.get('/api/v1/pending-users/%s/' %
                                   self.user.id)

        self.assert200(response)
        self.assertUserEqual(self.user, response.get_json())

    def test_user_delete(self):
        response = self.client.delete('/api/v1/pending-users/%s/' %
                                      self.user.id)
        self.assertStatus(response, 204)
