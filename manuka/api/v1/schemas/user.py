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

    id = ma.auto_field(column_name='keystone_user_id')
    external_ids = ma.Nested("NestedExternalIdSchema", many=True)

    class Meta:
        model = models.User
        load_instance = True
        include_relationships = True
        exclude = ('keystone_user_id',)


class UserUpdateSchema(ma.SQLAlchemyAutoSchema):

    id = ma.auto_field(column_name='keystone_user_id')

    class Meta:
        model = models.User
        load_instance = True
        fields = ('orcid', 'affiliation', 'ignore_username_not_email',
                  'mobile_number', 'phone_number')


class PendingUserSchema(ma.SQLAlchemyAutoSchema):

    external_ids = ma.Nested("NestedExternalIdSchema", many=True)

    class Meta:
        model = models.User
        load_instance = True
        include_relationships = True


class PendingUserUpdateSchema(ma.SQLAlchemyAutoSchema):

    class Meta:
        model = models.User
        load_instance = True
        fields = ('orcid', 'affiliation', 'ignore_username_not_email',
                  'mobile_number', 'phone_number')


user = UserSchema()
users = UserSchema(many=True)
user_update = UserUpdateSchema()
pending_user = PendingUserSchema()
pending_users = PendingUserSchema(many=True)
pending_user_update = PendingUserUpdateSchema()
