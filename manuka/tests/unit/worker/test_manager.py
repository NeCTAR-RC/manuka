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
from manuka.worker import manager as worker_manager


CONF = cfg.CONF

mock_app = mock.Mock()
mock_create_app = mock.Mock()
mock_create_app.return_value = mock_app


@mock.patch('manuka.create_app', new=mock_create_app)
class TestManager(base.TestCase):

    @mock.patch('manuka.common.clients.get_admin_keystoneclient')
    def test_sync_keystone_user(self, mock_keystone):

        mock_client = mock.Mock()
        mock_keystone.return_value = mock_client

        db_user = self.make_db_user()
        db.session.add(db_user)
        db.session.commit()
        manager = worker_manager.Manager()

        manager.sync_keystone_user(db_user.id)

        mock_client.users.get.assert_called_once_with(db_user.user_id)

    #def test_sync_keystone_user_sync_username(self):
        #manager = worker_manager.Manager()
        #manager.sync_keystone_user(user_id, set_username_as_email=True)
