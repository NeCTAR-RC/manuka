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

import flask
import flask_restful

from manuka.common import keystone
from manuka import policy
from manuka.common import policies


enforcer = policy.get_enforcer()


class Resource(flask_restful.Resource):

    def authorize(self, rule, target={}):
        rule = policies.PREFIX % rule
        enforcer.authorize(rule, target, self.oslo_context, do_raise=True)

    @property
    def oslo_context(self):
        return flask.request.environ.get(keystone.REQUEST_CONTEXT_ENV, None)
