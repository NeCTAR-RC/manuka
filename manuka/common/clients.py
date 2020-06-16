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

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client as ks_client
from novaclient import client as nova_client
from openstack import connection
from oslo_config import cfg
from oslo_log import log as logging
from swiftclient import client as swift_client
from . import orcid as orcid_client


LOG = logging.getLogger(__name__)
CONF = cfg.CONF

NOVA_VERSION = '2.60'


def get_session(token, project_id):
    auth = v3.Token(token=token,
                    auth_url=CONF.keystone.auth_url,
                    project_id=project_id,
                    project_domain_id='default')
    return session.Session(auth=auth)


def get_admin_keystoneclient(sesh):
    return ks_client.Client(session=sesh)


def get_openstack_client(project_id, token):
    auth_session = get_session(token, project_id)
    return connection.Connection(session=auth_session)


def get_nova_client(project_id, token):
    auth_session = get_session(token, project_id)
    return nova_client.Client(NOVA_VERSION, session=auth_session)


def get_admin_nova_client(sesh):
    return nova_client.Client(NOVA_VERSION, session=sesh)


def get_swift_client(sesh, project_id):
    os_opts = {}
    if project_id:
        endpoint = sesh.get_endpoint(service_type='object-store')
        auth_project = sesh.get_project_id()
        endpoint = endpoint.replace('AUTH_%s' % auth_project,
                                    'AUTH_%s' % project_id)
        os_opts['object_storage_url'] = '%s' % endpoint
    return swift_client.Connection(session=sesh, os_options=os_opts)

def get_orcid_client():
    return orcid_client.Client()
