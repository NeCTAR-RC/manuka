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

from manuka.common import email_utils
from manuka.tests.unit import base


@mock.patch('smtplib.SMTP')
class TestEmailUtils(base.TestCase):

    def test_send_email(self, mock_smtp_class):
        mock_smtp = mock.Mock()
        mock_smtp_class.return_value.__enter__.return_value = mock_smtp

        with mock.patch(
                'email.message.EmailMessage',
                autospec=True) as mock_email_message:
            msg = mock_email_message.return_value

            to = 'to@example.com'
            sender = 'from@example.com'
            subject = 'test subject'
            body = 'test body'

            email_utils.send_email(to, sender, subject, body)

            mock_smtp_class.asserrt_called_once_with('localhost')
            mock_smtp.send_message.assert_called_once_with(msg)
            msg.set_content.assert_called_with(body)
