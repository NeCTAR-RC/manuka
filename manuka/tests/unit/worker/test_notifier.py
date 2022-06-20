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

from manuka.tests.unit import base
from manuka.worker import notifier


CONF = cfg.CONF


class TestNotifier(base.TestCase):

    def test_render_template(self):
        template = notifier.render_template(
            'duplicate_account.tmpl',
            {'user': {'email': 'foo', 'fullname': 'Bob Smith'}})
        self.assertIn('Bob Smith', template)

    @mock.patch('taynacclient.client.Client')
    def test_send_message(self, mock_taynac):
        client = mock_taynac.return_value
        client.messages.send.return_value = {'backend_id': 123}

        message = notifier.send_message(
            session = mock.Mock(),
            email='owner@fake.org',
            context={'user': {'email': 'foo', 'fullname': 'Bob Smith'}},
            template='duplicate_account.tmpl',
            subject="Test subject")

        client.messages.send.assert_called_with(
            subject="Test subject",
            body=mock.ANY,
            recipient='owner@fake.org',
        )
        self.assertEqual(123, message.get('backend_id'))
