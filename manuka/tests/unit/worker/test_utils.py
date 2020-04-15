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
from manuka.worker import utils


CONF = cfg.CONF


class FakeUser(object):
    def __init__(self, username='fakeuser', name="Fake User",
                 email='fake@nectartest'):
        self.full_name = name
        self.username = username
        self.email = email


class FakeProject(object):
    def __init__(self, name='pt-21'):
        self.name = name


class TestUtils(base.TestCase):

    @mock.patch('manuka.common.email_utils.send_email')
    def test_send_welcome_email(self, mock_send_email):
        user = FakeUser()
        project = FakeProject()

        utils.send_welcome_email(user, project)
        # TODO(sorrison) Check content of body includes name and project name
        mock_send_email.assert_called_once_with(
            'fake@nectartest',
            CONF.smtp.from_email,
            'Welcome to NeCTAR Research Cloud - '
            'Project Trial Allocation created',
            mock.ANY,
            CONF.smtp.host)
