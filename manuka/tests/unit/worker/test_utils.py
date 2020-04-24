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

    def test_create_user(self):
        client = mock.Mock()
        name = 'user@nectar.org.au'
        email = 'user@nectar.org.au'
        project = '2fdfdfrr43frfr'
        full_name = 'nectar user'
        user = utils.create_user(client, name, email, project, full_name)
        client.users.create.assert_called_once_with(
            name=name, password=mock.ANY, email=email, domain='default',
            default_project=project)
        client.users.update.assert_called_once_with(
            client.users.create.return_value.id, full_name=full_name)
        self.assertEqual(client.users.update.return_value, user)

    def test_create_project(self):
        client = mock.Mock()
        name = 'project-name'
        description = 'project description'
        domain = 'project domain'
        project = utils.create_project(client, name, description, domain)
        client.projects.create.assert_called_once_with(
            name=name, domain=domain, description=description)
        self.assertEqual(client.projects.create.return_value, project)

    @mock.patch('manuka.worker.utils.get_roles')
    def test_add_user_roles(self, mock_get_roles):
        client = mock.Mock()
        user = mock.Mock()
        project = mock.Mock()
        roles = ['role1', 'role2']
        role1 = mock.Mock()
        role2 = mock.Mock()
        mock_get_roles.return_value = [role1, role2]

        utils.add_user_roles(client, user, project, roles)
        calls = [mock.call(user=user, project=project, role=role1),
                 mock.call(user=user, project=project, role=role2)]
        client.roles.grant.assert_has_calls(calls)

    def test_get_roles(self):
        client = mock.Mock()
        role_names = ['role1', 'role2']
        role1 = mock.Mock()
        role2 = mock.Mock()
        role3 = mock.Mock()
        role1.name = 'role1'
        role2.name = 'role2'
        role3.name = 'role3'

        client.roles.list.return_value = [role1, role2, role3]
        roles = utils.get_roles(client, role_names)

        client.roles.list.assert_called_once_with()
        self.assertEqual([role1, role2], roles)

    def test_get_domain_for_idp(self):
        domain = utils.get_domain_for_idp('http://idp1')
        self.assertEqual('default', domain)
        domain = utils.get_domain_for_idp('https://idp2')
        self.assertEqual('domain123', domain)

    @mock.patch('manuka.common.clients.get_openstack_client')
    def test_add_security_groups(self, mock_get_osc):
        token = 'fake'
        project_id = 'p123'
        user_id = 'u123'

        client = mock_get_osc.return_value

        utils.add_security_groups(user_id, project_id, token)

        mock_get_osc.assert_called_once_with(project_id, token)
        client.network.create_security_group.call_count = 3
        client.network.create_security_group_rule.call_count = 4

    @mock.patch('manuka.common.clients.get_admin_nova_client')
    def test_set_nova_quota(self, mock_get_nova):
        session = mock.Mock()
        project_id = 'p123'
        client = mock_get_nova.return_value

        utils.set_nova_quota(session, project_id)
        mock_get_nova.assert_called_once_with(session)
        client.quotas.update.assert_called_once_with(tenant_id=project_id,
                                                     cores=2,
                                                     instances=2,
                                                     ram=8192)

    @mock.patch('manuka.common.clients.get_swift_client')
    def test_set_swift_quota(self, mock_get_swift):
        session = mock.Mock()
        project_id = 'p123'
        quota_gb = 10
        client = mock_get_swift.return_value

        utils.set_swift_quota(session, project_id, quota_gb)
        mock_get_swift.assert_called_once_with(session, project_id=project_id)

        client.post_account.assert_called_once_with(
            headers={'x-account-meta-quota-bytes':
                     quota_gb * 1024 * 1024 * 1024})

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
