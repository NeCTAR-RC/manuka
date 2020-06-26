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

import copy
import operator
import socket
import sys

from keystoneauth1 import loading as ks_loading
from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging


LOG = logging.getLogger(__name__)


default_opts = [
    cfg.StrOpt('terms_version',
               default='v1'),
    cfg.StrOpt('support_url'),
    cfg.StrOpt('host',
               default=socket.gethostname()),
    cfg.StrOpt('idp_domain_mapping_dir',
               default='/etc/manuka/idp_domain_mappings'),
    cfg.StrOpt('default_target'),
    cfg.ListOpt('whitelist'),
    cfg.BoolOpt('fake_shib', default=False),
    cfg.BoolOpt('fake_shib_no_shib_orcid', default=False),
    cfg.StrOpt('auth_strategy', default='keystone',
               choices=['noauth',
                        'keystone',
                        'testing'],
               help="The auth strategy for API requests."),
]

flask_opts = [
    cfg.StrOpt('secret_key',
               secret=True),
    cfg.StrOpt('host',
               default='0.0.0.0'),
    cfg.IntOpt('port',
               default=5000),
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

orcid_opts = [
    cfg.StrOpt('key'),
    cfg.StrOpt('secret',
               secret=True),
    cfg.BoolOpt('sandbox',
                default=False),
]


cfg.CONF.register_opts(orcid_opts, group='orcid')
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


# Used by oslo-config-generator entry point
# https://docs.openstack.org/oslo.config/latest/cli/generator.html
def list_opts():
    return [
        ('DEFAULT', default_opts),
        ('orcid', orcid_opts),
        ('smtp', smtp_opts),
        ('keystone', keystone_opts),
        ('swift', swift_opts),
        ('worker', worker_opts),
        ('database', database_opts),
        ('flask', flask_opts),
        add_auth_opts(),
    ]


def add_auth_opts():
    opts = ks_loading.register_session_conf_options(cfg.CONF, 'service_auth')
    opt_list = copy.deepcopy(opts)
    opt_list.insert(0, ks_loading.get_auth_common_conf_options()[0])
    for plugin_option in ks_loading.get_auth_plugin_conf_options('password'):
        if all(option.name != plugin_option.name for option in opt_list):
            opt_list.append(plugin_option)
    opt_list.sort(key=operator.attrgetter('name'))
    return ('service_list', opt_list)
