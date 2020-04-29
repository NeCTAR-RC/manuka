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

    def get(self):
        try:
            self.authorize('list')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(403, message="Not authorised")

        db_users = db.session.query(models.User).all()
        return {'results': user.users_schema.dump(db_users)}


class UserSearch(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX

    def post(self):
        try:
            self.authorize('search')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(403, message="Not authorised")

        parser = reqparse.RequestParser()
        parser.add_argument('search', required=True)
        args = parser.parse_args()
        search = args.get('search')
        if len(search) < 3:
            flask_restful.abort(400,
                                message="Search must be at least 3 characters")
        db_users = db.session.query(models.User).filter(or_(
            models.User.email.ilike("%%%s%%" % search),
            models.User.displayname.ilike("%%%s%%" % search),
        )).all()

        return {'results': user.users_schema.dump(db_users)}


class User(base.Resource):

    POLICY_PREFIX = policies.USER_PREFIX

    def _get_user(self, id):
        return db.session.query(models.User).filter_by(id=id).first()

    def get(self, id):
        db_user = self._get_user(id)
        if not db_user:
            flask_restful.abort(404,
                                message="User {} doesn't exist".format(id))

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
        if not db_user:
            flask_restful.abort(404,
                                message="User {} doesn't exist".format(id))
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

    def _get_user(self, id):
        # Get the user that has logged in the most recently that is associated
        # with the given openstack user ID
        return db.session.query(models.User) \
                         .filter_by(user_id=id) \
                         .order_by(models.User.last_login.desc()).first()
