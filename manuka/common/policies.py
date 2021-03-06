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


CONF = cfg.CONF
_POLICY_PATH = '/etc/manuka/manuka.yaml'


enforcer = policy.Enforcer(CONF, policy_file=_POLICY_PATH)

ADMIN_OR_OWNER_OR_WRITER = 'admin_or_owner_or_writer'
ADMIN_OR_OWNER_OR_READER = 'admin_or_owner_or_reader'
ADMIN_OR_READER = 'admin_or_reader'
ADMIN_OR_WRITER = 'admin_or_writer'
ADMIN_OR_OWNER = 'admin_or_owner'


base_rules = [
    policy.RuleDefault(
        name='admin_required',
        check_str='role:admin or is_admin:1'),
    policy.RuleDefault(
        name='reader',
        check_str='role:reader or role:read_only '
                  'or role:cloud_admin or role:helpdesk'),
    policy.RuleDefault(
        name='writer',
        check_str='role:cloud_admin or role:helpdesk'),
    policy.RuleDefault(
        name='owner',
        check_str='user_id:%(user_id)s'),
    policy.RuleDefault(
        name=ADMIN_OR_OWNER,
        check_str='rule:admin_required or rule:owner'),
    policy.RuleDefault(
        name=ADMIN_OR_OWNER_OR_READER,
        check_str='rule:admin_or_owner or rule:reader'),
    policy.RuleDefault(
        name=ADMIN_OR_OWNER_OR_WRITER,
        check_str='rule:admin_or_owner or rule:writer'),
    policy.RuleDefault(
        name=ADMIN_OR_READER,
        check_str='rule:admin_required or rule:reader'),
    policy.RuleDefault(
        name=ADMIN_OR_WRITER,
        check_str='rule:admin_required or rule:writer'),
]

USER_PREFIX = "account:user:%s"

user_rules = [
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'get',
        check_str='rule:%s' % ADMIN_OR_OWNER_OR_READER,
        description='Show user details.',
        operations=[{'path': '/v1/users/{user_id}/',
                     'method': 'GET'},
                    {'path': '/v1/users/{user_id}/',
                     'method': 'HEAD'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'list',
        check_str='rule:admin_required',
        description='List users.',
        operations=[{'path': '/v1/users/',
                     'method': 'GET'},
                    {'path': '/v1/users/',
                     'method': 'HEAD'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'search',
        check_str='rule:%s' % ADMIN_OR_READER,
        description='Search users.',
        operations=[{'path': '/v1/users/search/',
                     'method': 'POST'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'update',
        check_str='rule:%s' % ADMIN_OR_OWNER,
        description='Update a user',
        operations=[{'path': '/v1/users/{user_id}/',
                     'method': 'PATCH'},
                    {'path': '/v1/users/{user_id}/refresh-orcid/',
                     'method': 'POST'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'delete',
        check_str='rule:%s' % ADMIN_OR_WRITER,
        description='Delete user.',
        operations=[{'path': '/v1/users/{user_id}/',
                     'method': 'DELETE'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'get_restricted_fields',
        check_str='rule:%s' % ADMIN_OR_READER,
        description='View restricted user fields',
        operations=[{'path': '/v1/users/{user_id}/',
                     'method': 'GET'},
                    {'path': '/v1/users/',
                     'method': 'GET'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'update_restricted_fields',
        check_str='rule:%s' % ADMIN_OR_WRITER,
        description='Update restricted user fields',
        operations=[{'path': '/v1/users/{user_id}/',
                     'method': 'PATCH'}]),
]

EXTERNAL_ID_PREFIX = "account:external-id:%s"

external_id_rules = [
    policy.DocumentedRuleDefault(
        name=EXTERNAL_ID_PREFIX % 'get',
        check_str='rule:%s' % ADMIN_OR_READER,
        description='Show external id details.',
        operations=[{'path': '/v1/external-ids/{external_id}/',
                     'method': 'GET'},
                    {'path': '/v1/external-ids/{external_id}/',
                     'method': 'HEAD'}]),
    policy.DocumentedRuleDefault(
        name=EXTERNAL_ID_PREFIX % 'update',
        check_str='rule:%s' % ADMIN_OR_WRITER,
        description='Update a external_id',
        operations=[{'path': '/v1/external-ids/{external_id}/',
                     'method': 'PATCH'}]),
    policy.DocumentedRuleDefault(
        name=EXTERNAL_ID_PREFIX % 'delete',
        check_str='rule:%s' % ADMIN_OR_WRITER,
        description='Delete external_id.',
        operations=[{'path': '/v1/external-ids/{external_id}/',
                     'method': 'DELETE'}]),
]


enforcer.register_defaults(base_rules)
enforcer.register_defaults(user_rules)
enforcer.register_defaults(external_id_rules)


def list_rules():
    return base_rules + user_rules + external_id_rules
