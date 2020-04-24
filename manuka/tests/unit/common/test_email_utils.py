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

from email.mime.text import MIMEText
from unittest import mock

from manuka.common import email_utils
from manuka.tests.unit import base


@mock.patch('smtplib.SMTP')
class TestViewsNoShib(base.TestCase):

    def test_send_email(self, mock_smtp_class):
        mock_smtp = mock.Mock()
        mock_smtp_class.return_value = mock_smtp
        to = 'to@example.com'
        sender = 'from@example.com'
        subject = 'test subject'
        body = 'test body'
        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to

        email_utils.send_email(to, sender, subject, body)

        mock_smtp_class.asserrt_called_once_with('localhost')
        mock_smtp.sendmail.assert_called_once_with(sender,
                                                   [to],
                                                   msg.as_string())
        mock_smtp.quit.assert_called_once_with()
