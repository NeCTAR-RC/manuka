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

from datetime import datetime
from datetime import timedelta
from unittest import mock
import werkzeug

from freezegun import freeze_time
from oslo_config import cfg

from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base
from manuka.tests.unit import fake_oidc
from manuka.tests.unit import fake_shib
from manuka import views


CONF = cfg.CONF


class TestModels(base.TestCase):
    def test_create_db_user(self):
        user, external_id = models.create_db_user(self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        external_ids = (
            db.session.query(models.ExternalId)
            .filter_by(user_id=user.id)
            .all()
        )
        self.assertEqual(1, len(external_ids))
        self.assertEqual(fake_shib.ID, external_ids[0].persistent_id)
        self.assertEqual(fake_shib.IDP, external_ids[0].idp)
        self.assertEqual("saml", external_ids[0].protocol)
        self.assertEqual(external_ids[0].user, db_user)
        self.assertEqual("new", db_user.state)
        self.assertTrue(db_user.has_protocol("saml"))
        self.assertFalse(db_user.has_protocol("oidc"))

    def test_create_db_user_oidc(self):
        attrs = dict(self.shib_attrs, id="sub-1234", idp="https://issuer")
        user, external_id = models.create_db_user(attrs, protocol="oidc")
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual("oidc", db_user.external_ids[0].protocol)
        self.assertEqual("https://issuer", db_user.external_ids[0].idp)
        self.assertEqual("sub-1234", db_user.external_ids[0].persistent_id)
        self.assertTrue(db_user.has_protocol("oidc"))
        self.assertFalse(db_user.has_protocol("saml"))

    def test_external_id_unknown_protocol(self):
        self.assertRaises(
            ValueError,
            models.ExternalId,
            models.User(),
            "1",
            {},
            protocol="ldap",
        )

    def test_external_id_protocol_default_in_db(self):
        # A row inserted without a protocol, as every pre-existing row
        # was, reads back as saml through the server default.
        user, external_id = self.make_db_user()
        db.session.execute(
            models.ExternalId.__table__.insert().values(
                user_id=user.id, persistent_id="legacy", attributes={}
            )
        )
        db.session.commit()
        legacy = (
            db.session.query(models.ExternalId)
            .filter_by(persistent_id="legacy")
            .one()
        )
        self.assertEqual("saml", legacy.protocol)
        self.assertEqual(2, len(user.external_ids))

    @freeze_time("2012-01-14")
    def test_update_db_user(self):
        # testing classic behavior: handling the mandatory attributes
        user, external_id = self.make_db_user()
        user.displayname = ""
        user.email = ""
        external_id.attributes = {}
        db.session.add(external_id)
        db.session.add(user)
        db.session.commit()
        models.update_db_user(user, external_id, self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual(self.shib_attrs["fullname"], db_user.displayname)
        self.assertEqual(self.shib_attrs["mail"], db_user.email)
        self.assertEqual(self.shib_attrs, db_user.external_ids[0].attributes)
        self.assertEqual(datetime(2012, 1, 14), db_user.last_login)

    def test_update_db_user_merging(self):
        # testing classic behavior: handling the mandatory attributes
        user, external_id = self.make_db_user()
        user.displayname = ""
        user.email = ""
        user.phone_number = "460 261"
        user.mobile_number = "0401 234 567"
        user.affiliation = "staff"
        user.orcid = "pretty"
        external_id.attributes = {
            "firstname": "George",
            "surname": "Cohen",
            "orcid": "ugly",
        }
        external_id.attributes.update(self.shib_attrs)
        self.shib_attrs.update(
            {
                "firstname": " Godfrey ",
                "surname": "Cohen",
                "telephonenumber": "1800 815 270",
                "orcid": "ugly",
            }
        )
        db.session.add(user)
        db.session.add(external_id)
        db.session.commit()

        models.update_db_user(user, external_id, self.shib_attrs)

        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual(self.shib_attrs["fullname"], db_user.displayname)
        self.assertEqual(self.shib_attrs["mail"], db_user.email)
        self.assertEqual(self.shib_attrs, db_user.external_ids[0].attributes)
        self.assertEqual("Godfrey", db_user.first_name)
        self.assertEqual("Cohen", db_user.surname)
        self.assertEqual("1800 815 270", db_user.phone_number)
        self.assertEqual("0401 234 567", db_user.mobile_number)
        self.assertEqual("staff", db_user.affiliation)
        self.assertIsNone(db_user.organisation)
        self.assertEqual("pretty", db_user.orcid)

    def test_update_bad_affiliation(self):
        user, external_id = self.make_db_user()
        self.shib_attrs.update({"affiliation": "parasite"})
        models.update_db_user(user, external_id, self.shib_attrs)
        db_user = db.session.query(models.User).get(user.id)
        self.assertEqual("member", db_user.affiliation)
        self.assertEqual(self.shib_attrs, db_user.external_ids[0].attributes)

    @mock.patch("keystoneauth1.identity.v3.Password")
    @mock.patch("manuka.models.keystone_client.Client")
    @mock.patch("manuka.common.clients.get_admin_keystoneclient")
    @mock.patch("manuka.models.sync_keystone_user")
    def test_keystone_authenticate(
        self,
        mock_sync_keystone_user,
        mock_get_admin_keystone_client,
        mock_keystone_client,
        mock_keystone_password,
    ):
        client = mock_get_admin_keystone_client.return_value
        keystone_user = client.users.get.return_value
        keystone_domain = client.domains.get.return_value
        user_client = mock_keystone_client.return_value
        updated_keystone_user = mock_sync_keystone_user.return_value
        p1 = mock.Mock()
        p2 = mock.Mock()
        user_client.projects.list.return_value = [p1, p2]
        db_user, external_id = self.make_db_user()

        token, project_id, user = models.keystone_authenticate(db_user)

        mock_sync_keystone_user.assert_called_once_with(
            client, db_user, keystone_user, False
        )
        client.users.get.assert_called_once_with(db_user.keystone_user_id)
        client.domains.get.assert_called_once_with(keystone_user.domain_id)

        mock_keystone_password.assert_called_once_with(
            username=updated_keystone_user.name,
            password=CONF.keystone.authenticate_password,
            auth_url=CONF.keystone.auth_url,
            user_domain_name=keystone_domain.name,
            project_domain_name="Default",
        )

        user_client.auth.client.get_token.assert_called_once_with()
        user_client.projects.list.assert_called_once_with(
            user=updated_keystone_user.id
        )

        self.assertEqual(user_client.auth.client.get_token.return_value, token)
        self.assertEqual(p1.id, project_id)
        self.assertEqual(updated_keystone_user, user)

    @mock.patch("keystoneauth1.identity.v3.Password")
    @mock.patch("manuka.models.keystone_client.Client")
    @mock.patch("manuka.common.clients.get_admin_keystoneclient")
    @mock.patch("manuka.models.sync_keystone_user")
    def test_keystone_authenticate_disabled(
        self,
        mock_sync_keystone_user,
        mock_get_admin_keystone_client,
        mock_keystone_client,
        mock_keystone_password,
    ):
        client = mock_get_admin_keystone_client.return_value
        keystone_user = mock.Mock(
            spec=["enabled", "domain_id"], enabled=False, domain_id="fake"
        )
        client.users.get.return_value = keystone_user
        user_client = mock_keystone_client.return_value

        db_user, external_id = self.make_db_user()

        self.assertRaises(
            werkzeug.exceptions.Unauthorized,
            models.keystone_authenticate,
            db_user,
        )

        mock_sync_keystone_user.assert_not_called()
        mock_keystone_password.assert_not_called()

        user_client.auth.client.get_token.assert_not_called()
        user_client.projects.list.assert_not_called()

    @mock.patch("keystoneauth1.identity.v3.Password")
    @mock.patch("manuka.models.keystone_client.Client")
    @mock.patch("manuka.common.clients.get_admin_keystoneclient")
    @mock.patch("manuka.models.sync_keystone_user")
    def test_keystone_authenticate_inactive(
        self,
        mock_sync_keystone_user,
        mock_get_admin_keystone_client,
        mock_keystone_client,
        mock_keystone_password,
    ):
        client = mock_get_admin_keystone_client.return_value
        keystone_user = mock.Mock(enabled=False, inactive=True)
        client.users.get.return_value = keystone_user
        keystone_domain = client.domains.get.return_value
        user_client = mock_keystone_client.return_value
        updated_keystone_user = mock_sync_keystone_user.return_value
        p1 = mock.Mock()
        p2 = mock.Mock()
        user_client.projects.list.return_value = [p1, p2]
        db_user, external_id = self.make_db_user(
            expiry_status="inactive", expiry_next_step=datetime(2013, 1, 1)
        )

        token, project_id, user = models.keystone_authenticate(db_user)
        client.users.update.assert_called_once_with(
            keystone_user, enabled=True, inactive=False
        )
        mock_sync_keystone_user.assert_called_once_with(
            client, db_user, keystone_user, False
        )
        client.users.get.assert_called_once_with(db_user.keystone_user_id)
        client.domains.get.assert_called_once_with(keystone_user.domain_id)

        mock_keystone_password.assert_called_once_with(
            username=updated_keystone_user.name,
            password=CONF.keystone.authenticate_password,
            auth_url=CONF.keystone.auth_url,
            user_domain_name=keystone_domain.name,
            project_domain_name="Default",
        )

        user_client.auth.client.get_token.assert_called_once_with()
        user_client.projects.list.assert_called_once_with(
            user=updated_keystone_user.id
        )

        self.assertEqual(user_client.auth.client.get_token.return_value, token)
        self.assertEqual(p1.id, project_id)
        self.assertEqual(updated_keystone_user, user)

    @mock.patch("manuka.common.clients.get_admin_keystoneclient")
    def test_sync_keystone_user(self, mock_keystone):
        keystone_user = mock.Mock(email="email1", full_name="name1")
        mock_client = mock_keystone.return_value
        mock_client.users.get.return_value = keystone_user

        db_user, external_id = self.make_db_user(email="email1")

        updated_keystone_user = models.sync_keystone_user(
            mock_client, db_user, keystone_user
        )

        mock_client.users.update.assert_called_once_with(
            keystone_user.id, full_name=db_user.displayname
        )
        self.assertEqual(
            mock_client.users.update.return_value, updated_keystone_user
        )

    @mock.patch("manuka.common.clients.get_admin_keystoneclient")
    def test_sync_keystone_user_sync_username(self, mock_keystone):
        keystone_user = mock.Mock(email="email1", full_name="name1")
        keystone_user.name = "oldname"
        mock_client = mock_keystone.return_value
        mock_client.users.get.return_value = keystone_user

        db_user, external_id = self.make_db_user(email="email1")

        updated_keystone_user = models.sync_keystone_user(
            mock_client, db_user, keystone_user, set_username_as_email=True
        )

        mock_client.users.update.assert_called_once_with(
            keystone_user.id, full_name=db_user.displayname, name="email1"
        )
        self.assertEqual(
            mock_client.users.update.return_value, updated_keystone_user
        )


class TestAutoLink(base.TestCase):
    """Matching a first OpenID Connect login to an existing SAML user."""

    def setUp(self):
        super().setUp()
        self.oidc_attrs = views.OIDCAttrMap.parse(fake_oidc.CLAIMS)
        self.next_id = 100

    def saml_user(self, state="created", keystone_user_id=0, **overrides):
        self.next_id += 1
        attrs = dict(self.shib_attrs, **overrides)
        return self.make_db_user(
            id=self.next_id,
            state=state,
            email=f"user{self.next_id}@example.com",
            keystone_user_id=keystone_user_id,
            persistent_id=f"pid-{self.next_id}",
            attrs=attrs,
        )

    def test_keys_are_produced_by_both_attribute_maps(self):
        for key, strong in models.AUTO_LINK_KEYS:
            self.assertIn(key, views.ShibbolethAttrMap.data.values())
            self.assertIn(key, views.OIDCAttrMap.data.values())
            self.assertIsInstance(strong, bool)
        self.assertNotIn("mail", [k for k, _ in models.AUTO_LINK_KEYS])
        self.assertNotIn("pairwise-id", [k for k, _ in models.AUTO_LINK_KEYS])

    def test_match_subject_id(self):
        self.saml_user(shared_token="other")
        user, external_id = self.saml_user(
            **{"subject-id": fake_oidc.SUBJECT_ID}
        )
        match = models.find_linkable_user(self.oidc_attrs)
        self.assertEqual(user, match.user)
        self.assertEqual("subject-id", match.key)
        self.assertEqual(external_id, match.external_id)

    def test_match_shared_token(self):
        user, external_id = self.saml_user(shared_token=fake_oidc.SHARED_TOKEN)
        match = models.find_linkable_user(self.oidc_attrs)
        self.assertEqual(user, match.user)
        self.assertEqual("shared_token", match.key)

    def test_match_eppn_recent_login(self):
        user, external_id = self.saml_user(eppn=fake_oidc.EPPN)
        external_id.last_login = datetime.now() - timedelta(days=10)
        db.session.commit()
        match = models.find_linkable_user(self.oidc_attrs)
        self.assertEqual(user, match.user)
        self.assertEqual("eppn", match.key)

    def test_match_eppn_stale_login(self):
        user, external_id = self.saml_user(eppn=fake_oidc.EPPN)
        external_id.last_login = datetime.now() - timedelta(days=200)
        db.session.commit()
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_match_eppn_never_logged_in(self):
        user, external_id = self.saml_user(eppn=fake_oidc.EPPN)
        self.assertIsNone(external_id.last_login)
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_match_eppn_window_configurable(self):
        CONF.set_override("eppn_autolink_max_age_days", 365, "oidc")
        user, external_id = self.saml_user(eppn=fake_oidc.EPPN)
        external_id.last_login = datetime.now() - timedelta(days=200)
        db.session.commit()
        self.assertEqual(user, models.find_linkable_user(self.oidc_attrs).user)

    def test_strong_key_wins_over_weaker(self):
        self.saml_user(shared_token=fake_oidc.SHARED_TOKEN)
        winner, _ = self.saml_user(**{"subject-id": fake_oidc.SUBJECT_ID})
        match = models.find_linkable_user(self.oidc_attrs)
        self.assertEqual(winner, match.user)
        self.assertEqual("subject-id", match.key)

    def test_ambiguous_strong_key_is_final(self):
        self.saml_user(**{"subject-id": fake_oidc.SUBJECT_ID})
        self.saml_user(**{"subject-id": fake_oidc.SUBJECT_ID})
        # A clean match on a weaker key must not rescue the ambiguity.
        self.saml_user(shared_token=fake_oidc.SHARED_TOKEN)
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_several_identities_of_one_user_is_a_match(self):
        user, _ = self.saml_user(shared_token=fake_oidc.SHARED_TOKEN)
        self.make_external_id(
            user,
            "pid-extra",
            attrs=dict(self.shib_attrs, shared_token=fake_oidc.SHARED_TOKEN),
        )
        self.assertEqual(user, models.find_linkable_user(self.oidc_attrs).user)

    def test_email_only_does_not_match(self):
        self.saml_user(mail=fake_oidc.EMAIL)
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_pairwise_id_does_not_match(self):
        self.saml_user(**{"pairwise-id": fake_oidc.PAIRWISE_ID})
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_requires_created_state(self):
        for state in ("new", "registered", "duplicate"):
            self.saml_user(state=state, shared_token=fake_oidc.SHARED_TOKEN)
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_requires_keystone_user(self):
        self.saml_user(
            keystone_user_id=None, shared_token=fake_oidc.SHARED_TOKEN
        )
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_requires_saml_identity(self):
        user, _ = self.saml_user()
        self.make_external_id(
            user,
            "other-sub",
            attrs=dict(self.oidc_attrs, id="other-sub"),
            protocol="oidc",
        )
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_user_already_linked(self):
        user, _ = self.saml_user(shared_token=fake_oidc.SHARED_TOKEN)
        self.make_external_id(
            user, "other-sub", attrs={"id": "other-sub"}, protocol="oidc"
        )
        self.assertIsNone(models.find_linkable_user(self.oidc_attrs))

    def test_no_identifiers_in_attrs(self):
        self.saml_user(shared_token=fake_oidc.SHARED_TOKEN)
        attrs = {"id": "x", "mail": fake_oidc.EMAIL, "fullname": "x"}
        self.assertIsNone(models.find_linkable_user(attrs))

    def test_attribute_lookup_with_hyphenated_key(self):
        user, external_id = self.saml_user(**{"subject-id": "abc@x"})
        rows = (
            db.session.query(models.ExternalId)
            .filter(models.external_id_attribute_equals("subject-id", "abc@x"))
            .all()
        )
        self.assertEqual([external_id], rows)
        rows = (
            db.session.query(models.ExternalId)
            .filter(models.external_id_attribute_equals("subject-id", "nope"))
            .all()
        )
        self.assertEqual([], rows)

    def test_link_external_id_seeds_profile_attributes(self):
        user, saml_id = self.saml_user(
            firstname="Godfrey",
            telephonenumber="1800 815 270",
            shared_token=fake_oidc.SHARED_TOKEN,
        )
        linked = models.link_external_id(
            user, self.oidc_attrs, "oidc", seed_from=saml_id
        )
        self.assertEqual("oidc", linked.protocol)
        self.assertEqual(fake_oidc.SUB, linked.persistent_id)
        self.assertEqual(fake_oidc.ISSUER, linked.idp)
        self.assertEqual(
            {"firstname": "Godfrey", "telephonenumber": "1800 815 270"},
            linked.attributes,
        )
        self.assertEqual(user, linked.user)
        self.assertTrue(user.has_protocol("oidc"))
        self.assertTrue(user.has_protocol("saml"))

    def test_link_external_id_without_seed(self):
        user, _ = self.saml_user()
        linked = models.link_external_id(user, self.oidc_attrs, "oidc")
        self.assertEqual({}, linked.attributes)

    def test_identity_drift(self):
        user, _ = self.saml_user()
        linked = self.make_external_id(
            user,
            fake_oidc.SUB,
            attrs=dict(self.oidc_attrs),
            protocol="oidc",
        )
        self.assertEqual([], models.identity_drift(linked, self.oidc_attrs))

        changed = dict(self.oidc_attrs, **{"subject-id": "someone-else"})
        self.assertEqual(
            ["subject-id"], models.identity_drift(linked, changed)
        )
        changed["shared_token"] = "other-token"
        self.assertEqual(
            ["subject-id", "shared_token"],
            models.identity_drift(linked, changed),
        )

    def test_identity_drift_ignores_absent_values(self):
        user, _ = self.saml_user()
        linked = self.make_external_id(
            user, fake_oidc.SUB, attrs={}, protocol="oidc"
        )
        self.assertEqual([], models.identity_drift(linked, self.oidc_attrs))
        linked.attributes = dict(self.oidc_attrs)
        without = {
            k: v
            for k, v in self.oidc_attrs.items()
            if k not in models.DRIFT_KEYS
        }
        self.assertEqual([], models.identity_drift(linked, without))


class TestMigrationReport(base.TestCase):
    def setUp(self):
        super().setUp()
        self.now = datetime.now()
        self.since = self.now - timedelta(days=180)
        self.next_id = 200

    def user(self, state="created", login_days_ago=10, **kwargs):
        self.next_id += 1
        attrs = dict(self.shib_attrs, **kwargs.pop("attrs", {}))
        user, external_id = self.make_db_user(
            id=self.next_id,
            state=state,
            email=f"user{self.next_id}@example.com",
            persistent_id=f"pid-{self.next_id}",
            attrs=attrs,
            **kwargs,
        )
        user.last_login = self.now - timedelta(days=login_days_ago)
        db.session.commit()
        return user

    def test_buckets(self):
        linked = self.user()
        self.make_external_id(
            linked, "sub-linked", attrs={"id": "sub-linked"}, protocol="oidc"
        )
        auto_subject = self.user(attrs={"subject-id": "abc@x"})
        auto_token = self.user(attrs={"shared_token": "tok"})
        action = self.user()
        action_eppn_only = self.user(attrs={"eppn": "e@x"})
        warning = self.user(expiry_status="warning")

        # Excluded: expired, not created, no keystone user, stale login.
        self.user(expiry_status="inactive")
        self.user(state="registered")
        self.user(keystone_user_id=None)
        self.user(login_days_ago=200)

        report = models.oidc_migration_report(self.since)
        self.assertEqual([linked], report["linked"])
        self.assertEqual([auto_subject, auto_token], report["auto"])
        self.assertEqual([action, action_eppn_only, warning], report["action"])

    def test_empty(self):
        report = models.oidc_migration_report(self.since)
        self.assertEqual({"linked": [], "auto": [], "action": []}, report)
