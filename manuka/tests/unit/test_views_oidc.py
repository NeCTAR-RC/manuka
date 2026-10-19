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

import time
from unittest import mock
from urllib import parse

from oslo_config import cfg

from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base
from manuka.tests.unit import fake_oidc
from manuka.tests.unit import fake_shib
from manuka import views


CONF = cfg.CONF

CALLBACK = "/oidc/callback?code=fake-code&state=fake-state"


class OIDCTestCase(base.TestCase):
    def setUp(self):
        super().setUp()
        self.oidc_client = self.patch_oidc_client()

    def set_oidc_session(self, attrs=None, expired=False):
        """Put a completed provider callback into the session."""
        if attrs is None:
            attrs = views.OIDCAttrMap.parse(self.oidc_claims)
        with self.client.session_transaction() as sess:
            sess["oidc_attrs"] = attrs
            sess["oidc_attrs_exp"] = int(time.time()) + (
                -1 if expired else 600
            )
        return attrs

    def mock_keystone_user(self, mock_keystone_authenticate):
        user = mock.Mock()
        user.configure_mock(name="test@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = "secret", "abcdef", user
        return user

    def external_ids(self):
        return db.session.query(models.ExternalId).all()

    def assertRedirectsTo(self, response, path, query=None):
        self.assertEqual(302, response.status_code)
        url = parse.urlparse(response.location)
        self.assertEqual(("http", "localhost", path), url[:3])
        self.assertEqual(query or {}, parse.parse_qs(url.query))


@mock.patch("manuka.views.worker_api", new=mock.Mock())
class TestOIDCLogin(OIDCTestCase):
    def test_disabled_404(self):
        CONF.set_override("enabled", False, "oidc")
        self.assert404(self.client.get("/oidc/login/"))
        self.assert404(self.client.get(CALLBACK))
        self.assert404(self.client.get("/oidc/continue/"))
        self.assert404(self.client.get("/oidc/logout/"))

    def test_login_redirects_to_provider(self):
        response = self.client.get("/oidc/login/")
        self.assertEqual(302, response.status_code)
        self.assertTrue(response.location.startswith(fake_oidc.AUTHORIZE_URL))
        self.assertEqual(
            [("http://localhost/oidc/callback", {})],
            self.oidc_client.redirect_calls,
        )
        with self.client.session_transaction() as sess:
            self.assertNotIn("oidc_return_path", sess)

    def test_login_derives_redirect_url_when_unset(self):
        CONF.set_override("redirect_url", None, "oidc")
        self.client.get("/oidc/login/")
        self.assertEqual(
            "http://localhost/oidc/callback",
            self.oidc_client.redirect_calls[0][0],
        )

    def test_login_stores_allowed_return_path(self):
        return_path = "https://test.example.com/auth/token"
        CONF.set_override("allow_list", [return_path])
        response = self.client.get(f"/oidc/login/?return-path={return_path}")
        self.assertEqual(302, response.status_code)
        with self.client.session_transaction() as sess:
            self.assertEqual(return_path, sess["oidc_return_path"])

    def test_login_rejects_bad_return_path(self):
        CONF.set_override(
            "allow_list", ["https://test.example.com/auth/token"]
        )
        response = self.client.get("/oidc/login/?return-path=http://bad")
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("title", "Authentication Error")
        self.assertEqual([], self.oidc_client.redirect_calls)
        with self.client.session_transaction() as sess:
            self.assertNotIn("oidc_return_path", sess)

    def test_login_clears_stale_state(self):
        with self.client.session_transaction() as sess:
            sess["_state_keycloak_old"] = {"data": "x"}
            sess["oidc_attrs"] = {"id": "stale"}
            sess["oidc_attrs_exp"] = int(time.time()) + 600
        self.client.get("/oidc/login/")
        with self.client.session_transaction() as sess:
            self.assertNotIn("_state_keycloak_old", sess)
            self.assertNotIn("oidc_attrs", sess)

    def test_callback_stores_attrs_and_redirects(self):
        response = self.client.get(CALLBACK)
        self.assertRedirectsTo(response, "/oidc/continue/")
        with self.client.session_transaction() as sess:
            attrs = sess["oidc_attrs"]
            self.assertEqual(fake_oidc.SUB, attrs["id"])
            self.assertEqual(fake_oidc.SUBJECT_ID, attrs["subject-id"])
            self.assertEqual(fake_oidc.PAIRWISE_ID, attrs["pairwise-id"])
            self.assertEqual(fake_oidc.SHARED_TOKEN, attrs["shared_token"])
            self.assertEqual(fake_oidc.ISSUER, attrs["idp"])
            self.assertEqual(fake_oidc.FEDERATION, attrs["federation"])
            self.assertGreater(sess["oidc_attrs_exp"], time.time())
        self.assertEqual([], self.external_ids())

    def test_callback_propagates_return_path(self):
        return_path = "https://test.example.com/auth/token"
        with self.client.session_transaction() as sess:
            sess["oidc_return_path"] = return_path
        response = self.client.get(CALLBACK)
        self.assertRedirectsTo(
            response, "/oidc/continue/", {"return-path": [return_path]}
        )
        with self.client.session_transaction() as sess:
            self.assertNotIn("oidc_return_path", sess)

    def test_callback_cookie_fits_budget(self):
        response = self.client.get(CALLBACK)
        for cookie in response.headers.getlist("Set-Cookie"):
            self.assertLess(len(cookie), 3500)

    def test_callback_provider_error_param(self):
        response = self.client.get(
            "/oidc/callback?error=access_denied"
            "&error_description=User+cancelled"
        )
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("title", "Login failed")
        self.assertContext("errors", ["User cancelled"])
        with self.client.session_transaction() as sess:
            self.assertNotIn("oidc_attrs", sess)

    def test_callback_token_exchange_error(self):
        self.oidc_client.error = "invalid_grant"
        response = self.client.get(CALLBACK)
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("title", "Login failed")
        with self.client.session_transaction() as sess:
            self.assertNotIn("oidc_attrs", sess)

    def test_callback_missing_claims(self):
        del self.oidc_client.claims["email"]
        del self.oidc_client.claims["name"]
        response = self.client.get(CALLBACK)
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("message", views.MISSING_ATTR_MSG["oidc"])
        self.assertContext(
            "errors",
            [
                "Required field 'email' can't be found.",
                "Required field 'name' can't be found.",
            ],
        )
        self.assertContext("support_url", CONF.support_url)

    def test_callback_bad_email(self):
        self.oidc_client.claims["email"] = "not an email"
        response = self.client.get(CALLBACK)
        self.assertTemplateUsed("error.html")
        self.assertIn("RFC 5322", response.get_data(as_text=True))

    def test_continue_without_session_redirects_to_login(self):
        response = self.client.get("/oidc/continue/")
        self.assertRedirectsTo(response, "/oidc/login/")

    def test_continue_without_session_keeps_return_path(self):
        response = self.client.get("/oidc/continue/?return-path=https://x/y")
        self.assertRedirectsTo(
            response, "/oidc/login/", {"return-path": ["https://x/y"]}
        )

    def test_continue_expired_session_redirects_to_login(self):
        self.set_oidc_session(expired=True)
        response = self.client.get("/oidc/continue/")
        self.assertRedirectsTo(response, "/oidc/login/")
        with self.client.session_transaction() as sess:
            self.assertNotIn("oidc_attrs", sess)

    def test_continue_unknown_subject_shows_choice(self):
        self.set_oidc_session()
        response = self.client.get("/oidc/continue/?return-path=https://x/y")
        self.assert200(response)
        self.assertTemplateUsed("choose_link.html")
        self.assertContext("email_known", False)
        self.assertContext("link_url", "/login/link/?return-path=https://x/y")
        body = response.get_data(as_text=True)
        self.assertIn(fake_oidc.DISPLAYNAME, body)
        self.assertIn('name="create_new"', body)
        self.assertIn('href="/login/link/?return-path=https://x/y"', body)
        self.assertEqual([], self.external_ids())
        self.assertEqual(0, db.session.query(models.User).count())
        with self.client.session_transaction() as sess:
            pending = sess["pending_oidc"]
            self.assertEqual(fake_oidc.SUB, pending["sub"])
            self.assertGreater(pending["exp"], time.time())
            self.assertGreaterEqual(len(pending["nonce"]), 16)

    def test_continue_unknown_subject_known_email(self):
        self.make_db_user(state="created", email=fake_oidc.EMAIL)
        self.set_oidc_session()
        response = self.client.get("/oidc/continue/")
        self.assertTemplateUsed("choose_link.html")
        self.assertContext("email_known", True)
        self.assertIn(
            "existing Nectar account", response.get_data(as_text=True)
        )

    def test_continue_create_new_shows_terms(self):
        attrs = self.set_oidc_session()
        response = self.client.post("/oidc/continue/", data={"create_new": 1})
        self.assert200(response)
        self.assertTemplateUsed("terms_form.html")
        self.assertContext("logout_url", "/oidc/logout/")

        external_ids = self.external_ids()
        self.assertEqual(1, len(external_ids))
        self.assertEqual("oidc", external_ids[0].protocol)
        self.assertEqual(fake_oidc.SUB, external_ids[0].persistent_id)
        self.assertEqual(fake_oidc.ISSUER, external_ids[0].idp)
        self.assertEqual(attrs, external_ids[0].attributes)
        self.assertEqual("new", external_ids[0].user.state)
        with self.client.session_transaction() as sess:
            self.assertEqual(external_ids[0].id, sess["external_id"])

    @mock.patch("manuka.models.update_db_user")
    def test_continue_agree_terms_registers(self, mock_update):
        self.set_oidc_session()
        self.client.post("/oidc/continue/", data={"create_new": 1})
        with mock.patch("manuka.views.worker_api") as mock_worker_api:
            response = self.client.post("/oidc/continue/", data={"agree": 1})
        self.assert200(response)
        self.assertTemplateUsed("creating_account.html")
        self.assertIn(
            'url: "/account_status"', response.get_data(as_text=True)
        )
        external_id = self.external_ids()[0]
        self.assertEqual("registered", external_id.user.state)
        mock_worker_api.WorkerAPI.return_value.create_user.assert_called_once()
        attrs = mock_worker_api.WorkerAPI.return_value.create_user.call_args[
            0
        ][1]
        self.assertEqual(fake_oidc.SUB, attrs["id"])

        status = self.client.get("/account_status")
        self.assertEqual(b'{"state": "registered"}', status.get_data())

    @mock.patch("manuka.models.keystone_authenticate")
    def test_continue_created_user_redirects(self, mock_keystone_authenticate):
        self.mock_keystone_user(mock_keystone_authenticate)
        db_user, external_id = self.make_db_user(
            state="created", persistent_id=fake_oidc.SUB, protocol="oidc"
        )
        self.set_oidc_session()
        response = self.client.get("/oidc/continue/")
        self.assert200(response)
        self.assertTemplateUsed("redirect.html")
        self.assertContext("target", CONF.default_target)
        self.assertContext("token", "secret")
        mock_keystone_authenticate.assert_called_once_with(
            db_user, set_username_as_email=False
        )
        self.assertIsNotNone(external_id.last_login)
        with self.client.session_transaction() as sess:
            self.assertEqual(external_id.id, sess["external_id"])

    @mock.patch("manuka.models.keystone_authenticate")
    def test_continue_ignores_saml_row_with_same_id(
        self, mock_keystone_authenticate
    ):
        # A SAML identity whose persistent id happens to equal the OIDC
        # subject must not be treated as the OIDC identity.
        self.make_db_user(state="created", persistent_id=fake_oidc.SUB)
        self.set_oidc_session()
        self.client.get("/oidc/continue/")
        self.assertTemplateUsed("choose_link.html")
        mock_keystone_authenticate.assert_not_called()

    @mock.patch("manuka.models.keystone_authenticate")
    def test_continue_return_path(self, mock_keystone_authenticate):
        self.mock_keystone_user(mock_keystone_authenticate)
        return_path = "https://test.example.com/auth/token"
        CONF.set_override("allow_list", [return_path])
        self.make_db_user(
            state="created", persistent_id=fake_oidc.SUB, protocol="oidc"
        )
        self.set_oidc_session()
        self.client.get(
            "/oidc/continue/", query_string={"return-path": return_path}
        )
        self.assertTemplateUsed("redirect.html")
        self.assertContext("target", return_path)

    @mock.patch("manuka.models.keystone_authenticate")
    def test_continue_return_path_revalidated(
        self, mock_keystone_authenticate
    ):
        self.mock_keystone_user(mock_keystone_authenticate)
        CONF.set_override(
            "allow_list", ["https://test.example.com/auth/token"]
        )
        self.make_db_user(
            state="created", persistent_id=fake_oidc.SUB, protocol="oidc"
        )
        self.set_oidc_session()
        response = self.client.get(
            "/oidc/continue/", query_string={"return-path": "http://bad"}
        )
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("title", "Authentication Error")

    @mock.patch("manuka.models.keystone_authenticate")
    def test_continue_username_form(self, mock_keystone_authenticate):
        user = self.mock_keystone_user(mock_keystone_authenticate)
        user.configure_mock(name="old@example.com")
        self.make_db_user(
            state="created", persistent_id=fake_oidc.SUB, protocol="oidc"
        )
        self.set_oidc_session()
        self.client.get("/oidc/continue/")
        self.assertTemplateUsed("username_form.html")

        # Keystone renames the user when asked to.
        user.configure_mock(name="test@example.com")
        self.client.post("/oidc/continue/", data={"change_username": True})
        self.assertTemplateUsed("redirect.html")
        mock_keystone_authenticate.assert_called_with(
            mock.ANY, set_username_as_email=True
        )

    def test_logout_clears_session_and_redirects(self):
        self.set_oidc_session()
        with self.client.session_transaction() as sess:
            sess["external_id"] = 1
        response = self.client.get("/oidc/logout/")
        self.assertEqual(302, response.status_code)
        url = parse.urlparse(response.location)
        self.assertEqual(
            fake_oidc.END_SESSION_URL, f"{url.scheme}://{url.netloc}{url.path}"
        )
        self.assertEqual(
            {
                "client_id": ["manuka"],
                "post_logout_redirect_uri": ["http://nectar.org.au/"],
            },
            parse.parse_qs(url.query),
        )
        with self.client.session_transaction() as sess:
            self.assertEqual({}, dict(sess))

    def test_logout_without_end_session_endpoint(self):
        CONF.set_override("post_logout_redirect_url", "https://home/", "oidc")
        self.oidc_client.load_server_metadata = lambda: {}
        response = self.client.get("/oidc/logout/")
        self.assertEqual(302, response.status_code)
        self.assertEqual("https://home/", response.location)


@mock.patch("manuka.views.rpc", new=mock.Mock())
@mock.patch("manuka.views.worker_api", new=mock.Mock())
class TestOIDCAutoLink(OIDCTestCase):
    def saml_user(self, **overrides):
        return self.make_db_user(
            state="created",
            email="old@example.com",
            attrs=dict(self.shib_attrs, **overrides),
        )

    @mock.patch("manuka.models.keystone_authenticate")
    def test_auto_links_existing_user(self, mock_keystone_authenticate):
        self.mock_keystone_user(mock_keystone_authenticate)
        db_user, saml_id = self.saml_user(shared_token=fake_oidc.SHARED_TOKEN)
        attrs = self.set_oidc_session()

        with self.assertLogs("manuka.views", level="INFO") as logs:
            response = self.client.get("/oidc/continue/")

        self.assert200(response)
        self.assertTemplateUsed("redirect.html")
        self.assertEqual(2, len(db_user.external_ids))
        oidc_id = [e for e in db_user.external_ids if e.protocol == "oidc"][0]
        self.assertEqual(fake_oidc.SUB, oidc_id.persistent_id)
        self.assertEqual(fake_oidc.ISSUER, oidc_id.idp)
        self.assertEqual(attrs, oidc_id.attributes)
        self.assertIsNotNone(oidc_id.last_login)
        self.assertEqual(1, db.session.query(models.User).count())
        with self.client.session_transaction() as sess:
            self.assertEqual(oidc_id.id, sess["external_id"])
        self.assertTrue(
            any("oidc.autolink" in line for line in logs.output), logs.output
        )

    @mock.patch("manuka.models.keystone_authenticate")
    def test_auto_link_keeps_user_profile_values(
        self, mock_keystone_authenticate
    ):
        self.mock_keystone_user(mock_keystone_authenticate)
        db_user, saml_id = self.saml_user(
            shared_token=fake_oidc.SHARED_TOKEN, telephonenumber="111"
        )
        db_user.phone_number = "999"  # set by the user through the API
        db.session.commit()
        self.oidc_claims["phone_number"] = "111"
        self.set_oidc_session()

        self.client.get("/oidc/continue/")
        self.assertTemplateUsed("redirect.html")
        self.assertEqual("999", db_user.phone_number)

    def test_no_auto_link_on_email(self):
        self.saml_user(mail=fake_oidc.EMAIL)
        self.set_oidc_session()
        self.client.get("/oidc/continue/")
        self.assertTemplateUsed("choose_link.html")
        self.assertEqual(1, len(self.external_ids()))

    def test_ambiguous_match_shows_choice(self):
        self.saml_user(shared_token=fake_oidc.SHARED_TOKEN)
        self.make_db_user(
            id=2,
            state="created",
            email="two@example.com",
            persistent_id="pid-2",
            attrs=dict(self.shib_attrs, shared_token=fake_oidc.SHARED_TOKEN),
        )
        self.set_oidc_session()
        with self.assertLogs("manuka.models", level="WARNING") as logs:
            self.client.get("/oidc/continue/")
        self.assertTemplateUsed("choose_link.html")
        self.assertTrue(
            any("oidc.link.ambiguous" in line for line in logs.output)
        )

    @mock.patch("manuka.models.keystone_authenticate")
    def test_known_subject_drift_warns(self, mock_keystone_authenticate):
        self.mock_keystone_user(mock_keystone_authenticate)
        attrs = self.set_oidc_session()
        self.make_db_user(
            state="created",
            persistent_id=fake_oidc.SUB,
            protocol="oidc",
            attrs=dict(attrs, shared_token="previous-token"),
        )
        with self.assertLogs("manuka.views", level="WARNING") as logs:
            response = self.client.get("/oidc/continue/")
        self.assert200(response)
        self.assertTemplateUsed("redirect.html")
        self.assertTrue(
            any("oidc.identity_drift" in line for line in logs.output)
        )

    @mock.patch("manuka.models.keystone_authenticate")
    def test_known_subject_drift_denied(self, mock_keystone_authenticate):
        CONF.set_override("deny_on_identity_drift", True, "oidc")
        attrs = self.set_oidc_session()
        self.make_db_user(
            state="created",
            persistent_id=fake_oidc.SUB,
            protocol="oidc",
            attrs=dict(attrs, **{"subject-id": "someone-else"}),
        )
        response = self.client.get("/oidc/continue/")
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("title", "Login blocked")
        mock_keystone_authenticate.assert_not_called()
        with self.client.session_transaction() as sess:
            self.assertNotIn("external_id", sess)


@mock.patch("manuka.views.rpc")
@mock.patch("manuka.views.worker_api", new=mock.Mock())
class TestOIDCLink(OIDCTestCase):
    """Linking the OIDC login in progress by Shibboleth re-authentication."""

    NONCE = "test-nonce-value"

    def setUp(self):
        super().setUp()
        # The Shibboleth identity presents a different email from the
        # OIDC one so the confirmation page visibly shows both.
        self.app.wsgi_app = fake_shib.TestShibWrapper(
            self.app.wsgi_app, mail="old@example.com"
        )
        self.oidc_attrs = self.set_oidc_session()

    def set_pending(self, sub=fake_oidc.SUB, expired=False):
        with self.client.session_transaction() as sess:
            sess["pending_oidc"] = {
                "sub": sub,
                "exp": int(time.time()) + (-1 if expired else 600),
                "nonce": self.NONCE,
            }

    def saml_user(self, state="created", **overrides):
        # fake_shib.TestShibWrapper presents persistent id fake_shib.ID.
        return self.make_db_user(
            state=state,
            email="old@example.com",
            attrs=dict(self.shib_attrs, **overrides),
        )

    def confirm(self, nonce=NONCE, **extra):
        data = {"confirm": "Link these accounts", "nonce": nonce}
        data.update(extra)
        return self.client.post("/login/link/", data=data)

    def assertLinkFailed(self, response, fragment):
        self.assert200(response)
        self.assertTemplateUsed("error.html")
        self.assertContext("title", "Account linking failed")
        self.assertIn(fragment, response.get_data(as_text=True))

    def test_get_shows_confirmation(self, mock_rpc):
        self.saml_user()
        self.set_pending()
        response = self.client.get("/login/link/")
        self.assert200(response)
        self.assertTemplateUsed("link_confirm.html")
        self.assertContext("nonce", self.NONCE)
        self.assertContext("oidc_attrs", self.oidc_attrs)
        body = response.get_data(as_text=True)
        # Both identities come from the live logins, not the database.
        self.assertIn("old@example.com", body)
        self.assertIn(fake_oidc.EMAIL, body)
        self.assertIn(fake_shib.IDP, body)
        self.assertIn(fake_oidc.HOME_ORG, body)
        self.assertIn(f'value="{self.NONCE}"', body)
        self.assertIn('href="/oidc/logout/"', body)
        self.assertEqual(1, len(self.external_ids()))

    def test_no_pending(self, mock_rpc):
        self.saml_user()
        response = self.client.get("/login/link/")
        self.assertLinkFailed(response, "expired or was not started")

    def test_expired_pending(self, mock_rpc):
        self.saml_user()
        self.set_pending(expired=True)
        self.assertLinkFailed(
            self.client.get("/login/link/"), "expired or was not started"
        )

    def test_pending_for_other_subject(self, mock_rpc):
        self.saml_user()
        self.set_pending(sub="someone-else")
        self.assertLinkFailed(
            self.client.get("/login/link/"), "expired or was not started"
        )

    def test_no_oidc_login_in_progress(self, mock_rpc):
        self.saml_user()
        self.set_pending()
        with self.client.session_transaction() as sess:
            del sess["oidc_attrs"]
        self.assertLinkFailed(
            self.client.get("/login/link/"), "expired or was not started"
        )

    def test_unknown_saml_user(self, mock_rpc):
        self.set_pending()
        self.assertLinkFailed(
            self.client.get("/login/link/"), "could not find an existing"
        )
        self.assertEqual([], self.external_ids())
        self.assertEqual(0, db.session.query(models.User).count())

    def test_saml_user_not_created(self, mock_rpc):
        self.saml_user(state="registered")
        self.set_pending()
        self.assertLinkFailed(
            self.client.get("/login/link/"), "could not find an existing"
        )

    def test_saml_user_without_keystone_account(self, mock_rpc):
        self.make_db_user(
            state="created", email="old@example.com", keystone_user_id=None
        )
        self.set_pending()
        self.assertLinkFailed(
            self.client.get("/login/link/"), "could not find an existing"
        )

    def test_user_already_linked(self, mock_rpc):
        user, _ = self.saml_user()
        self.make_external_id(
            user, "other-sub", attrs={"id": "other-sub"}, protocol="oidc"
        )
        self.set_pending()
        self.assertLinkFailed(
            self.client.get("/login/link/"), "already connected"
        )

    def test_conflicting_candidate(self, mock_rpc):
        self.saml_user()
        self.make_db_user(
            id=2,
            state="created",
            email="two@example.com",
            persistent_id="pid-2",
            attrs=dict(self.shib_attrs, shared_token=fake_oidc.SHARED_TOKEN),
        )
        self.set_pending()
        with self.assertLogs("manuka.views", level="WARNING") as logs:
            response = self.confirm()
        self.assertLinkFailed(response, "different Nectar account")
        self.assertTrue(
            any("oidc.link.refused" in line for line in logs.output)
        )
        self.assertEqual(2, len(self.external_ids()))

    def test_bad_nonce_rejected(self, mock_rpc):
        self.saml_user()
        self.set_pending()
        response = self.confirm(nonce="wrong")
        self.assertEqual(400, response.status_code)
        self.assertEqual(1, len(self.external_ids()))

    def test_missing_confirm_rejected(self, mock_rpc):
        self.saml_user()
        self.set_pending()
        response = self.client.post("/login/link/", data={"nonce": self.NONCE})
        self.assertEqual(400, response.status_code)
        self.assertEqual(1, len(self.external_ids()))

    def test_confirm_links_and_redirects(self, mock_rpc):
        db_user, saml_id = self.saml_user(
            firstname="Godfrey", telephonenumber="1800 815 270"
        )
        self.set_pending()
        with self.assertLogs("manuka.views", level="INFO") as logs:
            response = self.client.post(
                "/login/link/?return-path=https://x/y",
                data={"confirm": "1", "nonce": self.NONCE},
            )
        self.assertRedirectsTo(
            response, "/oidc/continue/", {"return-path": ["https://x/y"]}
        )

        self.assertEqual(2, len(db_user.external_ids))
        oidc_id = [e for e in db_user.external_ids if e.protocol == "oidc"][0]
        self.assertEqual(fake_oidc.SUB, oidc_id.persistent_id)
        self.assertEqual(fake_oidc.ISSUER, oidc_id.idp)
        self.assertEqual(
            {"firstname": "Godfrey", "telephonenumber": "1800 815 270"},
            oidc_id.attributes,
        )
        with self.client.session_transaction() as sess:
            self.assertEqual(oidc_id.id, sess["external_id"])
            self.assertNotIn("pending_oidc", sess)
            self.assertIn("oidc_attrs", sess)
        self.assertTrue(
            any("oidc.link.confirmed" in line for line in logs.output)
        )
        mock_rpc.get_notifier.return_value.info.assert_called_once_with(
            {},
            "account.external_id.link",
            {
                "user_id": db_user.keystone_user_id,
                "external_id": oidc_id.id,
                "protocol": "oidc",
                "idp": fake_oidc.ISSUER,
                "method": "shibboleth",
            },
        )

    @mock.patch("manuka.models.keystone_authenticate")
    def test_confirm_then_continue_logs_in(
        self, mock_keystone_authenticate, mock_rpc
    ):
        self.mock_keystone_user(mock_keystone_authenticate)
        db_user, saml_id = self.saml_user()
        self.set_pending()
        self.confirm()
        self.client.get("/oidc/continue/")
        self.assertTemplateUsed("redirect.html")
        mock_keystone_authenticate.assert_called_once_with(
            db_user, set_username_as_email=False
        )

    def test_confirm_subject_linked_meanwhile(self, mock_rpc):
        self.saml_user()
        self.make_db_user(
            id=2,
            state="created",
            email="two@example.com",
            persistent_id=fake_oidc.SUB,
            protocol="oidc",
            attrs={"id": fake_oidc.SUB},
        )
        self.set_pending()
        response = self.confirm()
        self.assertLinkFailed(response, "already been connected")
        self.assertEqual(2, len(self.external_ids()))
        mock_rpc.get_notifier.return_value.info.assert_not_called()

    def test_get_without_shibboleth_attributes(self, mock_rpc):
        self.app.wsgi_app = self.app.wsgi_app.app  # drop the fake
        self.set_pending()
        self.client.get("/login/link/")
        self.assertTemplateUsed("error.html")
        self.assertContext("message", views.MISSING_ATTR_MSG["saml"])
