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
from oslo_policy import opts as policy_opts
from oslo_policy import policy

from manuka.common import policies

CONF = cfg.CONF
_ENFORCER = None


def get_enforcer():
    global _ENFORCER
    if not _ENFORCER:
        # Defaults only, so operators can still override via
        # [oslo_policy] in manuka.conf.
        policy_opts.set_defaults(
            CONF, enforce_scope=True, enforce_new_defaults=True
        )
        _ENFORCER = policy.Enforcer(CONF)
        _ENFORCER.register_defaults(policies.list_rules())
    return _ENFORCER
