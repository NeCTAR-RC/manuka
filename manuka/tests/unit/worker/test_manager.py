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
from manuka.tests.unit import base
from manuka.worker import manager as worker_manager


CONF = cfg.CONF


@mock.patch('manuka.common.clients.get_admin_keystoneclient')
@mock.patch('manuka.create_app', new=mock.Mock())
class TestManager(base.TestCase):

    def test_sync_keystone_user(self, mock_keystone):
        keystone_user = mock.Mock(email='email1', full_name='name1')
        mock_client = mock.Mock()
        mock_keystone.return_value = mock_client
        mock_client.users.get.return_value = keystone_user

        db_user = self.make_db_user(email='email1')
        db.session.add(db_user)
        db.session.commit()

        manager = worker_manager.Manager()
        # Swap in our test app
        manager.app = self.app
        manager.sync_keystone_user(db_user.id)

        mock_client.users.get.assert_called_once_with(db_user.user_id)
        mock_client.users.update.assert_called_once_with(
            keystone_user.id, full_name=db_user.displayname)

    def test_sync_keystone_user_sync_username(self, mock_keystone):
        keystone_user = mock.Mock(email='email1', full_name='name1')
        keystone_user.name = 'oldname'
        mock_client = mock.Mock()
        mock_keystone.return_value = mock_client
        mock_client.users.get.return_value = keystone_user

        db_user = self.make_db_user(email='email1')
        db.session.add(db_user)
        db.session.commit()

        manager = worker_manager.Manager()
        # Swap in our test app
        manager.app = self.app
        manager.sync_keystone_user(db_user.id, set_username_as_email=True)

        mock_client.users.get.assert_called_once_with(db_user.user_id)
        mock_client.users.update.assert_called_once_with(
            keystone_user.id, full_name=db_user.displayname,
            name='email1')
