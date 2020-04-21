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

from oslo_config import cfg
from oslo_context import context

from manuka.common import keystone
from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base


CONF = cfg.CONF
USER_ID = 999


class TestKeystoneWrapper(object):

    def __init__(self, app, roles):
        self.app = app
        self.roles = roles

    def __call__(self, environ, start_response):
        cntx = context.RequestContext(roles=self.roles, user_id=USER_ID)
        environ[keystone.REQUEST_CONTEXT_ENV] = cntx

        return self.app(environ, start_response)


class TestUserApi(base.TestCase):

    ROLES = ['admin']

    def setUp(self):
        super().setUp()
        self.init_context()
        user = self.make_shib_user(state='new', agreed_terms=False,
                                   email='test@example.com')
        db.session.add(user)
        db.session.commit()
        self.user = user

    def init_context(self):
        self.app.wsgi_app = TestKeystoneWrapper(self.app.wsgi_app, self.ROLES)

    def assertUserEqual(self, user, user_dict):
        for key, value in user_dict.items():
            self.assertEqual(getattr(user, key), value)

    def test_user_list(self):
        response = self.client.get('/api/v1/users/')

        self.assert200(response)
        results = response.get_json().get('results')
        self.assertEqual(1, len(results))
        self.assertUserEqual(self.user, results[0])

    def test_user_get(self):
        response = self.client.get('/api/v1/users/%s/' % self.user.id)

        self.assert200(response)
        self.assertUserEqual(self.user, response.get_json())

    def test_user_update(self):
        new_orcid = 'new-orcid'
        data = {'orcid': new_orcid}
        response = self.client.patch('/api/v1/users/%s/' % self.user.id,
                                     json=data)

        self.assert200(response)
        self.user.orcid = new_orcid
        self.assertUserEqual(self.user, response.get_json())
        db_user = db.session.query(models.User).get(self.user.id)
        self.assertUserEqual(db_user, response.get_json())

    def _test_user_update_invalid(self, status):
        new_id = '2333'
        data = {'id': new_id}
        response = self.client.patch('/api/v1/users/%s/' % self.user.id,
                                     json=data)

        self.assertStatus(response, status)

    def test_user_update_invalid(self):
        self._test_user_update_invalid(401)


class TestUserApiUser(TestUserApi):

    ROLES = ['member']

    def setUp(self):
        super().setUp()
        user_self = self.make_shib_user(state='new', agreed_terms=False,
                                        email='test@example.com',
                                        id=USER_ID)
        db.session.add(user_self)
        db.session.commit()
        self.user_self = user_self

    def test_user_list(self):
        response = self.client.get('/api/v1/users/')
        self.assert403(response)

    def test_user_get(self):
        response = self.client.get('/api/v1/users/%s/' % self.user.id)
        self.assert404(response)

    def test_user_update(self):
        new_orcid = 'new-orcid'
        data = {'orcid': new_orcid}
        response = self.client.patch('/api/v1/users/%s/' % self.user.id,
                                     json=data)
        self.assert404(response)

    def test_user_get_self(self):
        response = self.client.get('/api/v1/users/%s/' % USER_ID)

        self.assert200(response)
        self.assertUserEqual(self.user_self, response.get_json())

    def test_user_update_self(self):
        new_orcid = 'new-orcid'
        data = {'orcid': new_orcid}
        response = self.client.patch('/api/v1/users/%s/' % USER_ID,
                                     json=data)
        self.assert200(response)
        self.user_self.orcid = new_orcid
        self.assertUserEqual(self.user_self, response.get_json())
        db_user = db.session.query(models.User).get(USER_ID)
        self.assertUserEqual(db_user, response.get_json())

    def test_user_update_invalid(self):
        self._test_user_update_invalid(404)
