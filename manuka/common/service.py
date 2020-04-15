from oslo_config import cfg

from manuka.common import rpc
from manuka import config


def prepare_service(argv=None):
    """Sets global config from config file and sets up logging."""
    argv = argv or []
    config.init(argv[1:])
    config.setup_logging(cfg.CONF)
    rpc.init()
