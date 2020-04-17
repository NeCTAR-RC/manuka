from oslo_config import cfg
from oslo_policy import policy


CONF = cfg.CONF
_POLICY_PATH = '/etc/manuka/manuka.yaml'


enforcer = policy.Enforcer(CONF, policy_file=_POLICY_PATH)

ADMIN_OR_OWNER_OR_WRITER = 'admin_or_owner_or_writer'
ADMIN_OR_OWNER_OR_READER = 'admin_or_owner_or_reader'
ADMIN_OR_READER = 'admin_or_reader'
ADMIN_OR_WRITER = 'admin_or_writer'


base_rules = [
    policy.RuleDefault(
        name='admin_required',
        check_str='role:admin or is_admin:1'),
    policy.RuleDefault(
        name='reader',
        check_str='role:reader or role:read_only'),
    policy.RuleDefault(
        name='writer',
        check_str='role:operator or role:helpdesk'),
    policy.RuleDefault(
        name='owner',
        check_str='user_id:%(user_id)s'),
    policy.RuleDefault(
        name='admin_or_owner',
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
        operations=[{'path': '/v1/users/{user_id}',
                     'method': 'GET'},
                    {'path': '/v1/users/{user_id}',
                     'method': 'HEAD'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'list',
        check_str='rule:%s' % ADMIN_OR_READER,
        description='List users.',
        operations=[{'path': '/v1/users',
                     'method': 'GET'},
                    {'path': '/v1/users',
                     'method': 'HEAD'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'update',
        check_str='rule:%s' % ADMIN_OR_OWNER_OR_WRITER,
        description='Update a user',
        operations=[{'path': '/v1/users/{user_id}',
                     'method': 'PATCH'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'get_restricted_fields',
        check_str='rule:%s' % ADMIN_OR_READER,
        description='View restricted user fields',
        operations=[{'path': '/v1/users/{user_id}',
                     'method': 'GET'},
                    {'path': '/v1/users',
                     'method': 'GET'}]),
    policy.DocumentedRuleDefault(
        name=USER_PREFIX % 'update_restricted_fields',
        check_str='rule:%s' % ADMIN_OR_WRITER,
        description='Update restricted user fields',
        operations=[{'path': '/v1/users/{user_id}',
                     'method': 'PATCH'}]),
]


enforcer.register_defaults(base_rules)
enforcer.register_defaults(user_rules)


def list_rules():
    return base_rules + user_rules
