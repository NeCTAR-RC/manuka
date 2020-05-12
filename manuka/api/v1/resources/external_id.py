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

from flask import request
import flask_restful
from oslo_log import log as logging
from oslo_policy import policy

from manuka.api.v1.resources import base
from manuka.api.v1.schemas import external_id as schemas
from manuka.common import policies
from manuka.extensions import db
from manuka import models


LOG = logging.getLogger(__name__)


class ExternalId(base.Resource):

    POLICY_PREFIX = policies.EXTERNAL_ID_PREFIX

    def _get_external_id(self, id):
        return db.session.query(models.ExternalId).filter_by(
            id=id).first_or_404()

    def get(self, id):
        external_id = self._get_external_id(id)

        target = {'user_id': external_id.user.keystone_user_id}
        try:
            self.authorize('get', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(
                404, message="External ID {} doesn't exist".format(id))

        return schemas.external_id.dump(external_id)

    def patch(self, id):
        external_id = self._get_external_id(id)

        data = request.get_json()
        user_id = data.get('user_id')
        if not user_id:
            flask_restful.abort(400, message="Must specify user_id")

        user = db.session.query(models.User) \
                         .filter_by(keystone_user_id=user_id).first_or_404()

        target = {'user_id': user.keystone_user_id}
        try:
            self.authorize('update', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404,
                                message="User {} dosn't exist".format(id))

        external_id.user = user
        db.session.add(external_id)
        db.session.commit()
        return schemas.external_id.dump(external_id)

    def delete(self, id):
        try:
            self.authorize('delete')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(
                404, message="External ID {} doesn't exist".format(id))

        external_id = self._get_external_id(id)
        db.session.delete(external_id)
        db.session.commit()
        return '', 204
