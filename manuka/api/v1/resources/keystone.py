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

import flask_restful
from oslo_log import log as logging
from oslo_policy import policy

from manuka.api.v1.resources import base
from manuka.common import clients
from manuka.common import keystone
from manuka.common import policies


LOG = logging.getLogger(__name__)


class UserByName(base.Resource):
    POLICY_PREFIX = policies.KEYSTONE_PREFIX

    def get(self, username):
        try:
            self.authorize("get_by_name")
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404, message=f"User {username} doesn't exist")

        k_session = keystone.KeystoneSession()
        session = k_session.get_session()
        client = clients.get_admin_keystoneclient(session)
        users = client.users.list(name=username)
        if len(users) == 0:
            flask_restful.abort(404, message=f"User {username} doesn't exist")
        elif len(users) > 1:
            flask_restful.abort(409, message="Multiple users exist")
        else:
            return users[0].to_dict()
