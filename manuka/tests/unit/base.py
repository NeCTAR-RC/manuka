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
from unittest import mock

import flask_testing
from oslo_config import cfg
from oslo_context import context

from manuka import app
from manuka.common import keystone
from manuka import extensions
from manuka.extensions import db
from manuka import models
from manuka.tests.unit import fake_shib


class TestCase(flask_testing.TestCase):

    def create_app(self):
        return app.create_app({
            'SECRET_KEY': 'secret',
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': "sqlite://",
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        }, conf_file='manuka/tests/etc/manuka.conf')

    def setUp(self):
        super().setUp()
        self.addCleanup(mock.patch.stopall)
        db.create_all()
        self.shib_attrs = {
            'mail': fake_shib.EMAIL,
            'fullname': fake_shib.DISPLAYNAME,
            'idp': fake_shib.IDP,
            'id': fake_shib.ID}

    def tearDown(self):
        super().tearDown()
        db.session.remove()
        db.drop_all()
        cfg.CONF.reset()
        extensions.api.resources = []

    def make_db_user(self, state='new', agreed_terms=True,
                     email='test@example.com', id=1324,
                     displayname='test user', keystone_user_id=0,
                     orcid='testorcid', expiry_status=None,
                     expiry_next_step=None):
        # create registered user
        db_user = models.User()
        db_user.id = id
        db_user.expiry_status = expiry_status
        db_user.expiry_next_step = expiry_next_step
        if keystone_user_id == 0:
            db_user.keystone_user_id = "ksid-%s" % id
        else:
            db_user.keystone_user_id = keystone_user_id
        db_user.email = email
        db_user.displayname = displayname

        if agreed_terms and state != 'new':
            date_now = datetime.datetime.now()
            db_user.registered_at = date_now
            db_user.terms_accepted_at = date_now
            db_user.terms_version = 'v1'
        else:
            db_user.registered_at = None
            db_user.terms_accepted_at = None
            db_user.terms_version = None
        db_user.state = state
        db_user.ignore_username_not_email = False
        db_user.orcid = orcid

        external_id = models.ExternalId(db_user, id, self.shib_attrs)
        external_id.idp = fake_shib.IDP
        db.session.add(db_user)
        db.session.add(external_id)
        db.session.commit()

        return db_user, external_id

    def create_terms(self, issued=datetime.date.today(), text='terms-text'):
        terms = models.Terms()
        terms.issued = issued
        terms.text = text
        db.session.add(terms)
        db.session.commit()
        return terms

    def assertTermsEqual(self, terms, api_terms):
        for key, value in api_terms.items():
            terms_value = getattr(terms, key)
            if type(getattr(terms, key)) == datetime.date:
                terms_value = terms_value.strftime('%Y-%m-%d')
            self.assertEqual(terms_value, value,
                             msg="%s attribute not equal" % key)

    def assertExternalIdsEqual(self, eids, api_eids):
        self.assertEqual(len(eids), len(api_eids))
        if eids is None:
            self.assertEqual({}, api_eids)
        else:
            self.assertEqual(len(eids), len(api_eids))
            db_idps = [e.idp for e in eids]
            api_idps = [e['idp'] for e in api_eids]
            self.assertEqual(db_idps, api_idps)

    def assertUserEqual(self, user, api_user, keystone_id_as_id=True):
        if user is None:
            user_dict = {}
        else:
            user_dict = user.__dict__
            if keystone_id_as_id:
                user_dict['id'] = user_dict.pop('keystone_user_id')
        for key, value in api_user.items():
            if key == 'external_ids':
                self.assertExternalIdsEqual(user.external_ids, value)
            else:
                user_value = user_dict.get(key)
                if type(user_value) == datetime.datetime:
                    user_value = user_value.strftime('%Y-%m-%dT%H:%M:%S.%f')

                self.assertEqual(user_value, value,
                                 msg="%s attribute not equal" % key)

    def assertExternalIdEqual(self, external_id, api_external_id):
        if external_id is None:
            external_id_dict = {}
        else:
            external_id_dict = external_id.__dict__
        for key, value in api_external_id.items():
            self.assertEqual(external_id_dict.get(key), value,
                             msg="%s attribute not equal" % key)


USER_ID = 999
KEYSTONE_USER_ID = 'ksid-999'


class TestKeystoneWrapper(object):

    def __init__(self, app, roles):
        self.app = app
        self.roles = roles

    def __call__(self, environ, start_response):
        cntx = context.RequestContext(roles=self.roles,
                                      user_id=KEYSTONE_USER_ID)
        environ[keystone.REQUEST_CONTEXT_ENV] = cntx

        return self.app(environ, start_response)


class ApiTestCase(TestCase):

    ROLES = ['admin']

    def setUp(self):
        super().setUp()
        self.init_context()

    def init_context(self):
        self.app.wsgi_app = TestKeystoneWrapper(self.app.wsgi_app, self.ROLES)
