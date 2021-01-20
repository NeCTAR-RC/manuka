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

import datetime

from manuka.tests.unit import base


class TestUserApiBase(base.ApiTestCase):

    def setUp(self):
        super().setUp()
        user, external_id = self.make_db_user(state='new', agreed_terms=False,
                                              email='test@example.com')
        self.user = user


class TestTermsApi(base.ApiTestCase):

    def setUp(self):
        super().setUp()
        terms = self.create_terms(issued=datetime.date(2019, 1, 1))
        current = self.create_terms()
        self.terms = terms
        self.current = current

    def test_terms_list(self):
        response = self.client.get('/api/v1/terms/')

        self.assert200(response)
        results = response.get_json().get('results')
        self.assertEqual(2, len(results))
        self.assertTermsEqual(self.terms, results[0])

    def test_terms_get(self):
        response = self.client.get('/api/v1/terms/%s/' %
                                   self.terms.id)

        self.assert200(response)
        self.assertTermsEqual(self.terms, response.get_json())

    def test_terms_current(self):
        response = self.client.get('/api/v1/terms/current/')

        self.assert200(response)
        self.assertTermsEqual(self.current, response.get_json())


class TestTermsUnauthenticatedAPI(TestTermsApi):

    def init_context(self):
        # Override and don't set keystone auth
        return
