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

import flask_testing
from oslo_config import cfg


from manuka import app
from manuka import extensions
from manuka.extensions import db


class TestCase(flask_testing.TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._buses = {}

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

    def tearDown(self):
        super().tearDown()
        db.session.remove()
        db.drop_all()
        cfg.CONF.reset()
        extensions.api.resources = []
