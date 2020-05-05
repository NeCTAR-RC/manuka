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
from manuka.api.v1.schemas import external_id
from manuka.common import policies
from manuka.extensions import db
from manuka import models


LOG = logging.getLogger(__name__)


class ExternalId(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX

    def _get_external_id(self, id):
        return db.session.query(models.ExternalId).filter_by(id=id).first()

    def get(self, id):
        db_external_id = self._get_external_id(id)
        if not db_external_id:
            flask_restful.abort(
                404, message="External_Id {} doesn't exist".format(id))

        target = {'user_id': db_external_id.user.user_id}
        try:
            self.authorize('get', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(
                404, message="External_Id {} doesn't exist".format(id))

        return external_id.external_id_schema.dump(db_external_id)
