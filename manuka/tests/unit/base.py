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

import fixtures
import flask_testing
from oslo_config import cfg
import oslo_messaging as messaging
from oslo_messaging import conffixture as messaging_conffixture
import testtools


import manuka
from manuka import app
from manuka.common import rpc
from manuka import extensions
from manuka.extensions import db
from manuka import models


class TestCase(flask_testing.TestCase):

    def create_app(self):
        app.register_resources(extensions.api)
        return manuka.create_app({
            'SECRET_KEY': 'secret',
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': "sqlite://",
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        }, conf_file='manuka/tests/settings.conf')

    def setUp(self):
        super().setUp()
        self.addCleanup(mock.patch.stopall)
        db.create_all()
        self.shib_attrs = {
            'mail': 'test@example.com',
            'fullname': 'john smith',
            'id': '1324'}

    def tearDown(self):
        super().tearDown()
        db.session.remove()
        db.drop_all()
        cfg.CONF.reset()
        extensions.api.resources = []

    def make_db_user(self, state='new', agreed_terms=True,
                       email='test@example.com', id=1324):
        # create registered user
        db_user = models.User(id)
        db_user.id = id
        db_user.user_id = id
        db_user.email = email
        db_user.shibboleth_attributes = self.shib_attrs

        if agreed_terms and state != 'new':
            date_now = datetime.now()
            db_user.registered_at = date_now
            db_user.terms_accepted_at = date_now
            db_user.terms_version = 'v1'
        else:
            db_user.registered_at = None
            db_user.terms_accepted_at = None
            db_user.terms_version = None
        db_user.state = state
        db_user.ignore_username_not_email = False
        db_user.orcid = 'testorchid'
        return db_user


class TestRpc(testtools.TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._buses = {}

    def _fake_create_transport(self, url):
        if url not in self._buses:
            self._buses[url] = messaging.get_rpc_transport(
                cfg.CONF,
                url=url)
        return self._buses[url]

    def setUp(self):
        super().setUp()
        self.addCleanup(rpc.cleanup)
        self.messaging_conf = messaging_conffixture.ConfFixture(cfg.CONF)
        self.messaging_conf.transport_url = 'fake:/'
        self.useFixture(self.messaging_conf)
        self.useFixture(fixtures.MonkeyPatch(
            'manuka.common.rpc.create_transport',
            self._fake_create_transport))
        with mock.patch('manuka.common.rpc.get_transport_url') as mock_gtu:
            mock_gtu.return_value = None
            rpc.init()
