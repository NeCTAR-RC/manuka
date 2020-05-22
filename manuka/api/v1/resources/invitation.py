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
from flask_restful import reqparse
from oslo_log import log as logging
from oslo_policy import policy

from manuka.api.v1.resources import base
from manuka.api.v1.schemas import invitation as schemas
from manuka.common import policies
from manuka.extensions import db
from manuka import models


LOG = logging.getLogger(__name__)


class InvitationList(base.Resource):

    POLICY_PREFIX = policies.INVITATION_PREFIX
    list_schema = schemas.invitations
    create_schema = schemas.create_invitation
    show_schema = schemas.invitation

    def _get_invitations(self, all_projects=False):
        query = db.session.query(models.Invitation)
        if not all_projects:
            query = query.filter_by(project_id=self.oslo_context.project_id)
        return query

    def get(self):
        try:
            self.authorize('list')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(403, message="Not authorised")

        parser = reqparse.RequestParser()
        parser.add_argument('limit', type=int)
        if self.authorize('list:all_projects', do_raise=False):
            parser.add_argument('all_projects', type=bool)

        args = parser.parse_args()
        query = self._get_invitations(all_projects=args.get('all_projects'))

        return self.paginate(query, args)

    def post(self):
        data = request.get_json()

        errors = self.create_schema.validate(data)
        if errors:
            flask_restful.abort(400, message=errors)

        try:
            self.authorize('create')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(403, message="Permission Denied")

        invitation = self.create_schema.load(data)
        invitation.project_id = self.oslo_context.project_id
        user = db.session.query(models.User) \
                         .filter_by(
                             keystone_user_id=self.oslo_context.user_id) \
                         .first_or_404()

        invitation.created_by = user
        db.session.add(invitation)
        db.session.commit()
        invitation.send()

        return self.show_schema.dump(invitation), 201


class Invitation(base.Resource):

    POLICY_PREFIX = policies.INVITATION_PREFIX
    schema = schemas.invitation

    def _get_invitation(self, id):
        return db.session.query(models.Invitation).get_or_404(id)

    def get(self, id):
        invitation = self._get_invitation(id)

        target = {'user_id': invitation.created_by.keystone_user_id}
        try:
            self.authorize('get', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(
                404, message="Invitation {} doesn't exist".format(id))

        return self.schema.dump(invitation)

    def delete(self, id):
        invitation = self._get_invitation(id)

        target = {'user_id': invitation.created_by.keystone_user_id}
        try:
            self.authorize('delete', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(
                404, message="Invitation {} doesn't exist".format(id))

        db.session.delete(invitation)
        db.session.commit()
        return '', 204
