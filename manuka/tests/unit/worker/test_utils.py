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
