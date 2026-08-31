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

from oslo_config import cfg
from oslo_policy import policy

from manuka.common import policies
from manuka.tests.unit import base


class TestPolicyDefaults(base.TestCase):
    def test_all_documented_rules_have_scope_types(self):
        for rule in policies.list_rules():
            if not isinstance(rule, policy.DocumentedRuleDefault):
                continue
            self.assertTrue(
                rule.scope_types,
                f"Policy rule {rule.name} has no scope_types",
            )
            self.assertTrue(
                set(rule.scope_types) <= {"system", "project"},
                f"Policy rule {rule.name} has unexpected scope_types "
                f"{rule.scope_types}",
            )

    def test_rules_register(self):
        # Catches dangling rule: references in check strings.
        enforcer = policy.Enforcer(cfg.CONF)
        enforcer.register_defaults(policies.list_rules())
        enforcer.load_rules()
        self.assertIn("system_reader", enforcer.rules)
