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

from oslo_config import cfg

from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base


CONF = cfg.CONF


class TestExternalIdApi(base.ApiTestCase):

    def setUp(self):
        super().setUp()
        user, external_id = self.make_db_user(state='created',
                                              email='test@example.com')
        self.user = user
        self.external_id = external_id

    def test_external_id_get(self):
        response = self.client.get('/api/v1/external-ids/%s/' %
                                   self.external_id.id)

        self.assert200(response)
        self.assertExternalIdEqual(self.external_id, response.get_json())

    def test_external_id_update(self):
        new_user, new_external_id = self.make_db_user(
            id=345, state='created', email='test2@example.com')

        self.assertEqual(1, len(new_user.external_ids))
        self.assertEqual(1, len(self.user.external_ids))
        data = {'user_id': new_user.keystone_user_id}
        response = self.client.patch('/api/v1/external-ids/%s/' %
                                     self.external_id.id,
                                     json=data)

        self.assert200(response)
        new_user = db.session.query(models.User).get(new_user.id)
        self.assertEqual(2, len(new_user.external_ids))
        old_user = db.session.query(models.User).get(self.user.id)
        self.assertEqual(0, len(old_user.external_ids))

        external_id = db.session.query(models.ExternalId).get(
            self.external_id.id)

        self.assertExternalIdEqual(external_id, response.get_json())

    def test_external_id_delete(self):
        response = self.client.delete('/api/v1/external-ids/%s/' %
                                      self.external_id.id)
        self.assertStatus(response, 204)
