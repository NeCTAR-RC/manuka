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
from manuka import models
from manuka.tests.unit import base
from manuka.tests.unit import fake_shib
from manuka import views


CONF = cfg.CONF


class MockIdentityService:
    def __init__(self, token):
        self.token = token

    def authenticate_shibboleth(self, id, project_id):
        return self.token


class TestShibbolethAttrMap(base.TestCase):
    def test_parse(self):
        environ = {"persistent-id": "1234", "mail": "Test@example.com"}
        self.assertEqual(
            views.ShibbolethAttrMap.parse(environ),
            {"id": "1234", "mail": "test@example.com"},
        )

    def test_attr(self):
        self.assertEqual(views.ShibbolethAttrMap.get_attr("mail"), "mail")
        self.assertEqual(views.ShibbolethAttrMap.get_attr("location"), "l")


MISSING_ATTR_MSG = [
    "Not enough details have been received from your "
    "institution to allow you to log on to the cloud. We "
    "need your id, your e-mail and your full name.",
    "Please contact your institution and tell them that "
    'their "AAF IdP" is broken!',
    "Copy and paste the details below into your email to "
    "your institution's support desk.",
    "The following required fields are missing or incorrect "
    "from the AAF service:",
]


@mock.patch("manuka.views.worker_api", new=mock.Mock())
class TestViewsNoShib(base.TestCase):
    def test_no_attrs(self):
        response = self.client.get("/login/")
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("message", MISSING_ATTR_MSG)
        self.assertContext(
            "errors",
            [
                "Required field 'displayName' can't be found.",
                "Required field 'mail' can't be found.",
                "Required field 'persistent-id' can't be found.",
            ],
        )


@mock.patch("manuka.views.worker_api", new=mock.Mock())
class TestViewsBadShib(base.TestCase):
    bad_email = "test@example.com;test2@example.com"

    def setUp(self):
        super().setUp()
        self.app.wsgi_app = fake_shib.TestShibWrapper(
            self.app.wsgi_app, mail=self.bad_email
        )

    def test_bad_mail_attr(self):
        response = self.client.get("/login/")
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("message", MISSING_ATTR_MSG)
        self.assertContext(
            "errors",
            [
                "The 'mail' field must be one RFC 5322 "
                "<addr-spec>: the value provided is "
                "'test@example.com;test2@example.com'"
            ],
        )


@mock.patch("manuka.views.worker_api", new=mock.Mock())
class TestViews(base.TestCase):
    def setUp(self):
        super().setUp()
        self.app.wsgi_app = fake_shib.TestShibWrapper(self.app.wsgi_app)

    def test_new_user(self):
        """Given a user who has registered
        And has accepted the terms of service
        When the user visits the site
        Then a keystone user will be created
        And the user will be redirected to the portal with
         a token encoded in the response.
        """

        response = self.client.get("/login/")
        self.assert200(response)
        self.assertTemplateUsed("terms_form.html")
        external_id = (
            db.session.query(models.ExternalId)
            .filter_by(persistent_id=fake_shib.ID)
            .first()
        )
        self.assertEqual(fake_shib.IDP, external_id.idp)

    @mock.patch("manuka.models.create_db_user")
    @mock.patch("manuka.models.update_db_user")
    def test_agreed_terms_user(self, mock_update, mock_create):
        """Given a known user who has not registered
        And has just accepted the terms of service
        When the user visits the site
        Then a keystone user will be created
        And the user will be redirected to the portal with
         a token encoded in the response.
        """

        # mock user
        user, external_id = self.make_db_user(state="new")
        mock_create.return_value = user

        # mock token
        token_string = (
            '{"access": {"serviceCatalog": [], "token": {"id": "aaaaaa"}}}'
        )
        token = mock.Mock()
        token.to_json.return_value = token_string

        response = self.client.post("/login/", data={"agree": True})

        # confirm that the keystone user was created
        mock_update.assert_called_once_with(
            user,
            user.external_ids[0],
            {
                "mail": fake_shib.EMAIL,
                "fullname": fake_shib.DISPLAYNAME,
                "id": fake_shib.ID,
                "idp": fake_shib.IDP,
            },
        )

        self.assertEqual(user.state, "registered")
        self.assert200(response)
        self.assertTemplateUsed("creating_account.html")

    def test_registered_user(self):
        """Given a user who has registered
        And has accepted the terms of service
        When the user visits the site
        Then a keystone user will be created
        And the user will be redirected to the portal with
         a token encoded in the response.
        """
        self.make_db_user(state="registered")
        response = self.client.get("/login/")
        self.assert200(response)
        self.assertTemplateUsed("creating_account.html")

    @mock.patch("manuka.models.create_db_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_created_user(self, mock_keystone_authenticate, mock_create):
        """Given a known user who has already has a keystone account
        When the user visits the site
        And the user will be redirected to the portal with
         a token encoded in the response.
        """
        self.make_db_user(state="created")

        # mock token
        token = "secret"
        project_id = "abcdef"
        user = mock.Mock()
        user.configure_mock(name="test@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.get("/login/")

        self.assert200(response)
        self.assertTemplateUsed("redirect.html")
        self.assertContext("tenant_id", project_id)
        self.assertContext("token", token)
        self.assertContext("target", CONF.default_target)

    @mock.patch("manuka.models.create_db_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_email_changed(self, mock_keystone_authenticate, mock_create):
        """Given a known user who's username is different to email

        User will be shown a form asking if they would like to
        change username
        """
        db_user, external_id = self.make_db_user(state="created")

        # mock token
        token = "secret"
        project_id = "abcdef"
        user = mock.Mock()
        user.configure_mock(name="foo@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.get("/login/")
        mock_keystone_authenticate.assert_called_once_with(
            db_user, set_username_as_email=False
        )

        # confirm that the redirect is passed correctly
        self.assert200(response)
        self.assertTemplateUsed("username_form.html")

    @mock.patch("manuka.models.create_db_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_email_changed_ignored(
        self, mock_keystone_authenticate, mock_create
    ):
        """Given a known user who's username is different to email

        User will be logged in as they ignored different email
        """
        self.make_db_user(state="created")

        # mock token
        token = "secret"
        project_id = "abcdef"
        user = mock.Mock()
        user.configure_mock(name="foo@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.post("/login/", data={"ignore_username": True})

        self.assert200(response)
        self.assertTemplateUsed("redirect.html")
        self.assertContext("tenant_id", project_id)
        self.assertContext("token", token)
        self.assertContext("target", CONF.default_target)

    @mock.patch("manuka.models.create_db_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_email_changed_submit(
        self, mock_keystone_authenticate, mock_create
    ):
        """Given a known user who's username is different to email

        User chosen to change username, then will be logged in
        """

        db_user, external_id = self.make_db_user(state="created")

        # mock token
        token = "secret"
        project_id = "abcdef"
        user = mock.Mock()
        user.configure_mock(name="test@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.post("/login/", data={"change_username": True})

        mock_keystone_authenticate.assert_called_once_with(
            db_user, set_username_as_email=True
        )

        self.assert200(response)
        self.assertTemplateUsed("redirect.html")
        self.assertContext("tenant_id", project_id)
        self.assertContext("token", token)
        self.assertContext("target", CONF.default_target)

    def test_new_terms(self):
        """Given a user who has registered
        And has accepted the terms of service but there
        is new terms to accept.
        """
        CONF.set_override("terms_version", "v2")

        self.make_db_user(state="registered")

        response = self.client.get("/login/")

        self.assert200(response)
        self.assertTemplateUsed("terms_form.html")

    @mock.patch("manuka.models.create_db_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_return_path(self, mock_keystone_authenticate, mock_create):
        """Redirect to a whitelisted return path specified in the query URL."""
        return_path = "https://test.example.com/auth/token"
        CONF.set_override("whitelist", [return_path])

        self.make_db_user(state="created")

        # mock token
        token = "secret"
        project_id = "abcdef"
        user = mock.Mock()
        user.configure_mock(name="test@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.get(f"/login/?return-path={return_path}")

        self.assert200(response)
        self.assertTemplateUsed("redirect.html")
        self.assertContext("tenant_id", project_id)
        self.assertContext("token", token)
        self.assertContext("target", return_path)

    @mock.patch("manuka.models.create_db_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_return_path_negative(
        self, mock_keystone_authenticate, mock_create
    ):
        """Redirect to a whitelisted return path specified in the query URL."""
        return_path = "https://test.example.com/auth/token"
        CONF.set_override("whitelist", [return_path])

        self.make_db_user(state="created")

        # mock token
        token = "secret"
        project_id = "abcdef"
        user = mock.Mock()
        user.configure_mock(name="test@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.get("/login/?return-path=http://bad")

        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("title", "Authentication Error")
        self.assertContext(
            "message",
            "You attempted to authenticate to the "
            "http://bad URL, "
            "which is not permitted by this service.",
        )

    @mock.patch("manuka.models.create_db_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_return_path_xss_escaped(
        self, mock_keystone_authenticate, mock_create
    ):
        """A rejected return-path is HTML-escaped in the error page.

        Regression test for a reflected XSS: the rejected URL is echoed
        into the error page, so it must be HTML-escaped in the output.
        """
        CONF.set_override("whitelist", ["https://test.example.com/auth/token"])

        self.make_db_user(state="created")

        token = "secret"
        project_id = "abcdef"
        user = mock.Mock()
        user.configure_mock(name="test@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        payload = "<script>alert(1)</script>"
        response = self.client.get(
            "/login/", query_string={"return-path": payload}
        )

        self.assert200(response)
        self.assertTemplateUsed("error.html")
        body = response.get_data(as_text=True)
        self.assertNotIn(payload, body)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", body)

    def test_account_status_no_user(self):
        response = self.client.get("/login/account_status")
        self.assert404(response)

    def test_account_status(self):
        self.make_db_user(state="registered")
        with self.client.session_transaction() as sess:
            sess["shib_user_id"] = "1324"
        response = self.client.get("/login/account_status")
        self.assert200(response)
        self.assertEqual(b'{"state": "registered"}', response.get_data())

    @mock.patch("manuka.common.clients.get_orcid_client")
    def test_orcid_link_no_code(self, mock_get_orcid_client):
        response = self.client.get("/orcid/link/")
        self.assertTemplateUsed("error.html")
        self.assertEqual(response.status_code, 400)
        self.assertContext("title", "Error")
        self.assertContext("message", "Invalid Request")

    @mock.patch("manuka.common.clients.get_orcid_client")
    def test_orcid_link_with_code(self, mock_get_orcid_client):
        mock_orcid_client = mock.Mock()
        mock_get_orcid_client.return_value = mock_orcid_client
        mock_orcid_client.get_token_from_authorization_code.return_value = {
            "orcid": "0000-0001-2345-6789",
            "access_token": "mock_access_token",
        }

        user, external_id = self.make_db_user(state="registered")
        with self.client.session_transaction() as sess:
            sess["shib_user_id"] = external_id.persistent_id

        response = self.client.get(
            "/orcid/link/?code=mock_code&next=http://example.org/next_page"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "http://example.org/next_page")

        self.assertEqual(user.orcid, "0000-0001-2345-6789")
        self.assertEqual(user.orcid_token, "mock_access_token")

    def test_orcid_unlink(self):
        user, external_id = self.make_db_user(state="registered")
        with self.client.session_transaction() as sess:
            sess["shib_user_id"] = external_id.persistent_id

        response = self.client.post(
            "/orcid/unlink/", data={"next": "http://example.org/next_page"}
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "http://example.org/next_page")

        self.assertIsNone(user.orcid)
        self.assertIsNone(user.orcid_token)

    def test_orcid_unlink_no_user(self):
        response = self.client.post(
            "/orcid/unlink/", data={"next": "http://example.org/next_page"}
        )
        self.assert404(response)

    def test_orcid_link_no_user(self):
        response = self.client.get("/orcid/link/?code=mock_code")
        self.assert404(response)

    @mock.patch("manuka.common.clients.get_orcid_client")
    def test_orcid_link_error(self, mock_get_orcid_client):
        mock_orcid_client = mock.Mock()
        mock_get_orcid_client.return_value = mock_orcid_client
        mock_orcid_client.get_token_from_authorization_code.side_effect = (
            Exception("ORCID Error")
        )

        user, external_id = self.make_db_user(state="registered")
        with self.client.session_transaction() as sess:
            sess["shib_user_id"] = external_id.persistent_id

        response = self.client.get(
            "/orcid/link/?code=mock_code&next=http://example.org/next_page"
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, "http://example.org/next_page")

        self.assertEqual("testorcid", user.orcid)
        self.assertIsNone(user.orcid_token)

    def test_orcid_unlink_no_next(self):
        user, external_id = self.make_db_user(state="registered")
        with self.client.session_transaction() as sess:
            sess["shib_user_id"] = external_id.persistent_id

        response = self.client.post("/orcid/unlink/")
        self.assertEqual(response.status_code, 400)

        self.assertIsNotNone(user.orcid)
