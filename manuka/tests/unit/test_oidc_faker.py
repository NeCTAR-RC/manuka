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
from urllib import parse

from oslo_config import cfg

from manuka import oidc
from manuka import oidc_faker
from manuka.tests.unit import base


CONF = cfg.CONF


@mock.patch("manuka.views.worker_api", new=mock.Mock())
class TestOIDCFaker(base.TestCase):
    def setUp(self):
        super().setUp()
        CONF.set_override("fake", True, "oidc")

    def test_get_client_returns_fake(self):
        self.assertIsInstance(oidc.get_client(), oidc_faker.FakeOIDCClient)

    def test_get_client_real_when_not_fake(self):
        CONF.set_override("fake", False, "oidc")
        self.assertNotIsInstance(oidc.get_client(), oidc_faker.FakeOIDCClient)

    def test_fake_route_absent_when_disabled(self):
        CONF.set_override("fake", False, "oidc")
        self.assert404(self.client.get("/oidc/fake/"))

    def test_round_trip(self):
        response = self.client.get("/oidc/login/")
        self.assertEqual(302, response.status_code)
        url = parse.urlparse(response.location)
        self.assertEqual("/oidc/fake/", url.path)
        self.assertEqual(
            ["http://localhost/oidc/callback"],
            parse.parse_qs(url.query)["redirect_uri"],
        )

        response = self.client.get(response.location)
        self.assert200(response)
        self.assertIn("FAKE OIDC PROVIDER", response.get_data(as_text=True))

        response = self.client.post(
            "/oidc/fake/",
            data={
                "fakeoidc": "Log in",
                "redirect_uri": "http://localhost/oidc/callback",
                "sub": "fake-sub-7",
                "email": "Dev@Example.edu",
                "name": "Dev User",
                "au_edu_person_shared_token": "tok-7",
                "edu_person_affiliation": "staff",
                "federation": "tuakiri",
            },
        )
        self.assertEqual(302, response.status_code)
        self.assertTrue(
            response.location.startswith("http://localhost/oidc/callback?")
        )

        response = self.client.get(response.location)
        self.assertEqual(302, response.status_code)
        self.assertTrue(response.location.endswith("/oidc/continue/"))
        with self.client.session_transaction() as sess:
            attrs = sess["oidc_attrs"]
        self.assertEqual("fake-sub-7", attrs["id"])
        self.assertEqual("dev@example.edu", attrs["mail"])
        self.assertEqual("tok-7", attrs["shared_token"])
        self.assertEqual(oidc_faker.FAKE_ISSUER, attrs["idp"])
        self.assertEqual("tuakiri", attrs["federation"])
        self.assertNotIn("eppn", attrs)

        response = self.client.get("/oidc/continue/")
        self.assertTemplateUsed("choose_link.html")

    def test_logout_without_end_session(self):
        response = self.client.get("/oidc/logout/")
        self.assertEqual(302, response.status_code)
        self.assertEqual(CONF.oidc.post_logout_redirect_url, response.location)
