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

from manuka.cmd import manage
from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base
from manuka.tests.unit import fake_shib


class TestManage(base.TestCase):
    def invoke(self, command, *args):
        runner = self.app.test_cli_runner()
        result = runner.invoke(command, args)
        self.assertEqual(0, result.exit_code, result.output)
        return result.output

    def test_add_domain_mapping(self):
        self.invoke(manage.add_domain_mapping, "domain-1", "tuakiri")
        mapping = (
            db.session.query(models.DomainIdpMapping)
            .filter_by(idp_entity_id="tuakiri")
            .one()
        )
        self.assertEqual("domain-1", mapping.domain_id)

        self.invoke(manage.add_domain_mapping, "domain-2", "tuakiri")
        mapping = (
            db.session.query(models.DomainIdpMapping)
            .filter_by(idp_entity_id="tuakiri")
            .one()
        )
        self.assertEqual("domain-2", mapping.domain_id)

    def _users(self):
        now = datetime.now()
        linked, _ = self.make_db_user(
            id=1, state="created", email="linked@example.com"
        )
        self.make_external_id(
            linked, "sub-1", attrs={"id": "sub-1"}, protocol="oidc"
        )
        action, _ = self.make_db_user(
            id=2,
            state="created",
            email="action@example.com",
            persistent_id="pid-2",
        )
        stale, _ = self.make_db_user(
            id=3,
            state="created",
            email="stale@example.com",
            persistent_id="pid-3",
        )
        linked.last_login = now - timedelta(days=1)
        action.last_login = now - timedelta(days=100)
        stale.last_login = now - timedelta(days=300)
        db.session.commit()

    def test_migration_report_csv(self):
        self._users()
        output = self.invoke(manage.oidc_migration_report)
        lines = output.strip().splitlines()
        self.assertEqual(
            "keystone_user_id,email,displayname,last_login,saml_idp",
            lines[0],
        )
        self.assertEqual(2, len(lines))
        self.assertTrue(lines[1].startswith("ksid-2,action@example.com,"))
        self.assertTrue(lines[1].endswith(f",{fake_shib.IDP}"))

    def test_migration_report_window(self):
        self._users()
        output = self.invoke(manage.oidc_migration_report, "--days", "365")
        self.assertIn("action@example.com", output)
        self.assertIn("stale@example.com", output)

    def test_migration_report_bucket(self):
        self._users()
        output = self.invoke(
            manage.oidc_migration_report, "--bucket", "linked"
        )
        self.assertIn("linked@example.com", output)
        self.assertNotIn("action@example.com", output)

    def test_migration_report_summary(self):
        self._users()
        output = self.invoke(manage.oidc_migration_report, "--summary")
        self.assertEqual("linked: 1\nauto: 0\naction: 1\n", output)
