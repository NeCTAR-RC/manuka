from oslo_config import cfg
from oslo_policy import policy

from manuka import policies

CONF = cfg.CONF
_ENFORCER = None


def get_enforcer():
    CONF([], project='manuka')
    global _ENFORCER
    if not _ENFORCER:
        _ENFORCER = policy.Enforcer(CONF)
        _ENFORCER.register_defaults(policies.list_rules())
    return _ENFORCER
