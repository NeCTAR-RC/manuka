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

from manuka.api.v1.resources import external_id
from manuka.api.v1.resources import user


def initialize_resources(api):
    api.add_resource(user.UserList, '/v1/users/')
    api.add_resource(user.User, '/v1/users/<id>/')
    api.add_resource(user.PendingUserList, '/v1/pending-users/')
    api.add_resource(user.PendingUser, '/v1/pending-users/<id>/')
    api.add_resource(user.UserSearch, '/v1/users/search/')
    api.add_resource(user.UserByOpenstackUserID, '/v1/users-os/<id>/')
    api.add_resource(external_id.ExternalId, '/v1/external-ids/<id>/')
