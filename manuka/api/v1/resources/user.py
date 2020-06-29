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

import json

from flask import request
import flask_restful
from flask_restful import reqparse
from oslo_log import log as logging
from oslo_policy import policy
from requests import exceptions
from sqlalchemy import or_

from manuka.api.v1.resources import base
from manuka.api.v1.schemas import user as schemas
from manuka.common import clients
from manuka.common import keystone
from manuka.common import policies
from manuka.extensions import db
from manuka import models
from manuka.worker import utils


LOG = logging.getLogger(__name__)


class UserList(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX
    schema = schemas.users

    def _get_users(self):
        return db.session.query(models.User) \
            .filter(models.User.keystone_user_id.isnot(None))

    def get(self, **kwargs):
        try:
            self.authorize('list')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(403, message="Not authorised")

        parser = reqparse.RequestParser()
        parser.add_argument('registered_at__lt')
        parser.add_argument('state')
        parser.add_argument('limit', type=int)
        args = parser.parse_args()

        query = self._get_users()
        registered_at__lt = args.get('registered_at__lt')

        if registered_at__lt:
            query = query.filter(
                models.User.registered_at < registered_at__lt)
        if args.get('state'):
            query = query.filter(
                models.User.state == args.get('state'))
        query = query.order_by(models.User.keystone_user_id)
        return self.paginate(query, args)


class UserSearch(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX
    schema = schemas.users

    def post(self):
        try:
            self.authorize('search')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(403, message="Not authorised")

        parser = reqparse.RequestParser()
        parser.add_argument('search', required=True)
        parser.add_argument('limit', type=int)
        args = parser.parse_args()
        search = args.get('search')
        if len(search) < 3:
            flask_restful.abort(400,
                                message="Search must be at least 3 characters")

        query = db.session.query(models.User)
        query = query.filter(models.User.keystone_user_id.isnot(None))
        query = query.filter(or_(
            models.User.email.ilike("%%%s%%" % search),
            models.User.displayname.ilike("%%%s%%" % search)))

        query = query.order_by(models.User.keystone_user_id)
        return self.paginate(query, args)


class User(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX
    schema = schemas.user
    update_schema = schemas.user_update

    def _get_user(self, id):
        return db.session.query(models.User) \
                         .filter_by(keystone_user_id=id).first_or_404()

    def get(self, id):
        db_user = self._get_user(id)

        target = {'user_id': db_user.keystone_user_id}
        try:
            self.authorize('get', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404,
                                message="User {} doesn't exist".format(id))

        return self.schema.dump(db_user)

    def patch(self, id):
        data = request.get_json()

        errors = schemas.user.validate(data)
        if errors:
            flask_restful.abort(400, message=errors)

        db_user = self._get_user(id)
        target = {'user_id': db_user.keystone_user_id}
        try:
            self.authorize('update', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404,
                                message="User {} dosn't exist".format(id))

        errors = self.update_schema.validate(data)
        if errors:
            flask_restful.abort(401, message="Not authorized to edit ")

        db_user = self.update_schema.load(data, instance=db_user)
        db.session.commit()

        return self.schema.dump(db_user)


class RefreshOrcid(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX
    schema = schemas.user

    def _get_user(self, id):
        return db.session.query(models.User) \
                         .filter_by(keystone_user_id=id).first_or_404()

    def post(self, id):
        db_user = self._get_user(id)
        target = {'user_id': db_user.keystone_user_id}
        try:
            self.authorize('refresh_orcid', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404,
                                message="User {} doesn't exist".format(id))
        try:
            utils.refresh_orcid(db_user)
            return self.schema.dump(db_user)
        except exceptions.HTTPError as ex:
            LOG.info("Orcid refresh failed (%s): url = %s",
                     db_user.keystone_user_id,
                     ex.response.status_code,
                     ex.request.url)
            flask_restful.abort(400, message="Orcid refresh failed")


class ProjectsWithRole(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX

    def _get_user(self, id):
        return db.session.query(models.User) \
                         .filter_by(keystone_user_id=id).first_or_404()

    def post(self, id):
        db_user = self._get_user(id)
        target = {'user_id': db_user.keystone_user_id}
        try:
            self.authorize('projects', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404,
                                message="User {} doesn't exist".format(id))

        parser = reqparse.RequestParser()
        parser.add_argument('role_name', required=True)
        args = parser.parse_args()
        role_name = args.get('role_name')

        k_session = keystone.KeystoneSession()
        session = k_session.get_session()
        client = clients.get_admin_keystoneclient(session)
        roles = utils.get_roles(client, [role_name])
        if roles:
            ra_list = client.role_assignments.list(
                user=db_user.keystone_user_id,
                role=roles[0])
            return json.dumps([ra.scope['project']['id'] for ra in ra_list])
        else:
            flask_restful.abort(
                400,
                message="Role {} doesn't exist".format(role_name))


# Transition API used by dashboard user info module
class UserByOpenstackUserID(User):
    pass


class PendingUserList(UserList):

    schema = schemas.pending_users
    update_schema = schemas.pending_user_update

    def _get_users(self):
        return db.session.query(models.User).filter_by(keystone_user_id=None)


class PendingUser(User):

    schema = schemas.pending_user

    def _get_user(self, id):
        return db.session.query(models.User).filter_by(keystone_user_id=None) \
                                            .filter_by(id=id).first_or_404()

    def delete(self, id):
        try:
            self.authorize('delete')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404,
                                message="User {} doesn't exist".format(id))

        db_user = self._get_user(id)
        db.session.delete(db_user)
        db.session.commit()
        return '', 204
