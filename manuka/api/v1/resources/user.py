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
from oslo_policy import policy

from manuka.api.v1.resources import base
from manuka.api.v1.schemas import user
from manuka.extensions import db
from manuka import models


class UserList(base.Resource):

    def get(self):
        try:
            self.authorize('list_users')
        except policy.PolicyNotAuthorized:
            flask_restful.abort(403, message="Not authorised")

        db_users = db.session.query(models.User).all()
        return {'results': user.users_schema.dump(db_users)}


class User(base.Resource):

    def get(self, id):
        db_user = db.session.query(models.User).filter_by(id=id).first()
        target = {'user_id': db_user.user_id}
        try:
            self.authorize('get_user', target)
        except policy.PolicyNotAuthorized:
            flask_restful.abort(404, message="User {} doesn't exist".format(id))
        return user.user_schema.dump(db_user)
