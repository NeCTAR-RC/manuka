import socket
import sys

from keystoneauth1 import loading as ks_loading
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging


LOG = logging.getLogger(__name__)


default_opts = [
    cfg.StrOpt('terms_version',
               default='v2'),
    cfg.StrOpt('support_url'),
    cfg.StrOpt('host',
               default=socket.gethostname()),
    cfg.StrOpt('idp_domain_mapping_dir',
               default='/etc/manuka/idp_domain_mappings'),
    cfg.StrOpt('default_target'),
    cfg.MultiStrOpt('whitelist'),
]

flask_opts = [
    cfg.StrOpt('secret_key',
               secret=True),
]

database_opts = [
    cfg.StrOpt('connection'),
]

worker_opts = [
    cfg.IntOpt('workers',
               default=1),
]

swift_opts = [
    cfg.IntOpt('default_quota_gb',
               default=None)
]

keystone_opts = [
    cfg.StrOpt('authenticate_password',
               secret=True,
               default=None),
    cfg.StrOpt('auth_url'),
]

smtp_opts = [
    cfg.StrOpt('host',
               default='localhost'),
    cfg.StrOpt('from_email',)
]


cfg.CONF.register_opts(smtp_opts, group='smtp')
cfg.CONF.register_opts(keystone_opts, group='keystone')
cfg.CONF.register_opts(swift_opts, group='swift')
cfg.CONF.register_opts(worker_opts, group='worker')
cfg.CONF.register_opts(database_opts, group='database')
cfg.CONF.register_opts(flask_opts, group='flask')
cfg.CONF.register_opts(default_opts)

logging.register_options(cfg.CONF)

oslo_messaging.set_transport_defaults(control_exchange='manuka')

ks_loading.register_auth_conf_options(cfg.CONF, 'service_auth')
ks_loading.register_session_conf_options(cfg.CONF, 'service_auth')


def init(args=[], conf_file='/etc/manuka/manuka.conf'):
    cfg.CONF(
        args,
        project='manuka',
        default_config_files=[conf_file])


def setup_logging(conf):
    """Sets up the logging options for a log with supplied name.

    :param conf: a cfg.ConfOpts object
    """
    product_name = "manuka"
    logging.setup(conf, product_name)
    LOG.info("Logging enabled!")
    LOG.debug("command line: %s", " ".join(sys.argv))
