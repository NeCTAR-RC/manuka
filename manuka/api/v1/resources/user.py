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
from sqlalchemy import or_

from manuka.api.v1.resources import base
from manuka.api.v1.schemas import user
from manuka.common import policies
from manuka.extensions import db
from manuka import models


LOG = logging.getLogger(__name__)


class UserList(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX

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

        query = db.session.query(models.User)
        query = query.filter(models.User.keystone_user_id.isnot(None))
        registered_at__lt = args.get('registered_at__lt')

        if registered_at__lt:
            query = query.filter(
                models.User.registered_at < registered_at__lt)
        if args.get('state'):
            query = query.filter(
                models.User.state == args.get('state'))
        query = query.order_by(models.User.keystone_user_id)
        return self.paginate(query, user.users_schema, args)


class UserSearch(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX

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
        return self.paginate(query, user.users_schema, args)


class User(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX

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

        return user.user_schema.dump(db_user)

    def patch(self, id, **kwargs):
        data = request.get_json()

        errors = user.user_schema.validate(data)
        if errors:
            flask_restful.abort(400, message=errors)

        db_user = self._get_user(id)
        target = {'user_id': db_user.keystone_user_id}
        try:
            self.authorize('update', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404,
                                message="User {} doesn't exist".format(id))

        errors = user.user_update_schema.validate(data)
        if errors:
            flask_restful.abort(401, message="Not authorized to edit ")

        db_user = user.user_schema.load(data, instance=db_user)
        db.session.commit()

        return user.user_schema.dump(db_user)


# Transition API used by dashboard user info module
class UserByOpenstackUserID(User):
    pass
