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


# Fields that are only visible and updatable to privileged callers.  See
# the ``get_restricted_fields`` and ``update_restricted_fields`` policies.
RESTRICTED_FIELDS = ("expiry_status", "expiry_next_step")


class UserSchema(ma.SQLAlchemyAutoSchema):
    id = ma.auto_field(column_name="keystone_user_id")
    external_ids = ma.Nested("ExternalIdSchema", many=True)

    class Meta:
        model = models.User
        load_instance = True
        include_relationships = True
        exclude = ("keystone_user_id", "orcid_token")


class UserUpdateSchema(ma.SQLAlchemyAutoSchema):
    id = ma.auto_field(column_name="keystone_user_id")

    class Meta:
        model = models.User
        load_instance = True
        fields = (
            "affiliation",
            "ignore_username_not_email",
            "mobile_number",
            "phone_number",
            "expiry_status",
            "expiry_next_step",
        )


class PendingUserSchema(ma.SQLAlchemyAutoSchema):
    external_ids = ma.Nested("ExternalIdSchema", many=True)

    class Meta:
        model = models.User
        load_instance = True
        include_relationships = True
        exclude = ("orcid_token",)


class PendingUserUpdateSchema(ma.SQLAlchemyAutoSchema):
    class Meta:
        model = models.User
        load_instance = True
        fields = (
            "affiliation",
            "ignore_username_not_email",
            "mobile_number",
            "phone_number",
        )


user = UserSchema()
user_limited = UserSchema(exclude=RESTRICTED_FIELDS)
users = UserSchema(many=True)
user_update = UserUpdateSchema()
user_update_limited = UserUpdateSchema(exclude=RESTRICTED_FIELDS)
pending_user = PendingUserSchema()
pending_user_limited = PendingUserSchema(exclude=RESTRICTED_FIELDS)
pending_users = PendingUserSchema(many=True)
pending_user_update = PendingUserUpdateSchema()
