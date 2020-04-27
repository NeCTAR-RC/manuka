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

from manuka.extensions import ma
from manuka import models


class UserSchema(ma.SQLAlchemyAutoSchema):

    class Meta:
        model = models.User
        load_instance = True


class UserUpdateSchema(ma.SQLAlchemyAutoSchema):

    class Meta:
        model = models.User
        load_instance = True
        fields = ('orcid', 'affiliation', 'ignore_username_not_email',
                  'mobile_number', 'phone_number')


user_schema = UserSchema()
users_schema = UserSchema(many=True)
user_update_schema = UserUpdateSchema()
