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


class ExternalIdSchema(ma.SQLAlchemyAutoSchema):

    class Meta:
        model = models.ExternalId
        load_instance = True
        exclude = ('id',)


external_id_schema = ExternalIdSchema()
