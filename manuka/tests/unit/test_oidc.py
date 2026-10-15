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

import flask
from oslo_config import cfg

from manuka import config
from manuka import oidc
from manuka.tests.unit import base
from manuka.tests.unit import fake_oidc


CONF = cfg.CONF

METADATA_URL = (
    "https://keycloak.example/realms/nectar/.well-known/openid-configuration"
)


class TestInitApp(base.TestCase):
    @mock.patch("manuka.oidc.OAuth")
    def test_registers_client(self, mock_oauth):
        app = flask.Flask("test")
        client = oidc.init_app(app)

        mock_oauth.assert_called_once_with(app)
        mock_oauth.return_value.register.assert_called_once_with(
            "keycloak",
            client_id="manuka",
            client_secret="test",
            server_metadata_url=METADATA_URL,
            client_kwargs={
                "scope": "openid profile email",
                "code_challenge_method": "S256",
            },
        )
        self.assertEqual(mock_oauth.return_value.register.return_value, client)
        self.assertEqual(
            mock_oauth.return_value, app.extensions[oidc.EXTENSION_KEY]
        )

    @mock.patch("manuka.oidc.OAuth")
    def test_disabled_does_not_register(self, mock_oauth):
        CONF.set_override("enabled", False, "oidc")
        app = flask.Flask("test")
        self.assertIsNone(oidc.init_app(app))
        mock_oauth.return_value.register.assert_not_called()

    def test_server_metadata_url_from_issuer(self):
        CONF.set_override("issuer", "https://sso.example/realms/x/", "oidc")
        self.assertEqual(
            "https://sso.example/realms/x/.well-known/openid-configuration",
            oidc.server_metadata_url(),
        )

    def test_server_metadata_url_explicit(self):
        CONF.set_override("server_metadata_url", "https://meta/x", "oidc")
        self.assertEqual("https://meta/x", oidc.server_metadata_url())

    def test_get_client(self):
        client = oidc.get_client()
        self.assertEqual("manuka", client.client_id)
        self.assertEqual("S256", client.client_kwargs["code_challenge_method"])
        self.assertEqual("openid profile email", client.client_kwargs["scope"])

    def test_get_client_without_extension(self):
        with flask.Flask("bare").app_context():
            self.assertIsNone(oidc.get_client())

    def test_list_opts_includes_oidc(self):
        groups = dict(config.list_opts())
        self.assertIs(config.oidc_opts, groups["oidc"])


class TestFetchClaims(base.TestCase):
    def test_id_token_claims(self):
        client = fake_oidc.FakeOIDCClient()
        claims = oidc.fetch_claims(client, client.authorize_access_token())
        self.assertEqual(fake_oidc.SUB, claims["sub"])
        self.assertEqual(fake_oidc.ISSUER, claims["iss"])
        self.assertEqual(fake_oidc.EMAIL, claims["email"])
        self.assertEqual(0, client.userinfo_calls)

    def test_userinfo_merged(self):
        CONF.set_override("use_userinfo_endpoint", True, "oidc")
        client = fake_oidc.FakeOIDCClient(
            userinfo={"sub": fake_oidc.SUB, "phone_number": "123"}
        )
        claims = oidc.fetch_claims(client, client.authorize_access_token())
        self.assertEqual("123", claims["phone_number"])
        self.assertEqual(fake_oidc.EMAIL, claims["email"])
        self.assertEqual(1, client.userinfo_calls)

    def test_userinfo_subject_mismatch(self):
        CONF.set_override("use_userinfo_endpoint", True, "oidc")
        client = fake_oidc.FakeOIDCClient(
            userinfo={"sub": "someone-else", "email": "x@example.com"}
        )
        self.assertRaises(
            oidc.OIDCError,
            oidc.fetch_claims,
            client,
            client.authorize_access_token(),
        )

    def test_missing_subject(self):
        claims = dict(fake_oidc.CLAIMS)
        del claims["sub"]
        client = fake_oidc.FakeOIDCClient(claims)
        self.assertRaises(
            oidc.OIDCError,
            oidc.fetch_claims,
            client,
            client.authorize_access_token(),
        )

    def test_missing_issuer(self):
        claims = dict(fake_oidc.CLAIMS, iss="")
        client = fake_oidc.FakeOIDCClient(claims)
        self.assertRaises(
            oidc.OIDCError,
            oidc.fetch_claims,
            client,
            client.authorize_access_token(),
        )

    def test_no_userinfo_in_token(self):
        client = fake_oidc.FakeOIDCClient()
        self.assertRaises(
            oidc.OIDCError, oidc.fetch_claims, client, {"access_token": "x"}
        )
