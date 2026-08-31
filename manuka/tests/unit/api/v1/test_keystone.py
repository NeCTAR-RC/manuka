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

from keystoneclient.v3 import users

from manuka.tests.unit import base


class TestKeystoneApi(base.ApiTestCase):
    @mock.patch("manuka.common.clients.get_admin_keystoneclient")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_user_by_name(self, mock_ks_auth, mock_get_keystone):
        client = mock_get_keystone.return_value
        user_info = {
            "username": "bob",
            "description": "bob user",
            "domain_id": "123",
            "email": "bob@bob.com",
            "enabled": True,
        }
        keystone_user = users.User(manager=None, info=user_info)

        client.users.list.return_value = [keystone_user]

        response = self.client.get("/api/v1/keystone-ext/user-by-name/bob/")
        self.assert200(response)
        self.assertEqual(user_info, response.get_json())


class TestKeystoneApiSystemScoped(TestKeystoneApi):
    """A system-scoped admin token has the same access as a project admin."""

    SYSTEM_SCOPE = "all"


class TestKeystoneApiSystemReader(TestKeystoneApi):
    """A system-scoped reader token can look up keystone users."""

    ROLES = ["reader"]
    SYSTEM_SCOPE = "all"


class TestKeystoneApiProjectReader(base.ApiTestCase):
    """A project-scoped reader token gets no access.

    The reader role only grants read access when system-scoped.
    """

    ROLES = ["reader"]

    def test_user_by_name(self):
        response = self.client.get("/api/v1/keystone-ext/user-by-name/bob/")
        self.assert404(response)


class TestKeystoneApiDomainScoped(base.ApiTestCase):
    """Domain-scoped tokens are rejected by scope enforcement."""

    ROLES = ["admin"]
    DOMAIN_ID = base.DOMAIN_ID

    def test_user_by_name(self):
        response = self.client.get("/api/v1/keystone-ext/user-by-name/bob/")
        self.assert404(response)
