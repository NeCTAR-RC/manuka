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
import datetime

from oslo_config import cfg

from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base


CONF = cfg.CONF


class TestInvitationApi(base.ApiTestCase):

    ROLES = ['TenantManager']

    def make_invitation(self, user, project_id=base.KEYSTONE_PROJECT_ID):
        invitation = models.Invitation(email='new-user1@example.org')
        invitation.created_by = user
        invitation.project_id = project_id
        db.session.add(invitation)
        db.session.commit()
        return invitation

    def assertInvitationEqual(self, invitation, api_invitation):
        if invitation is None:
            invitation_dict = {}
        else:
            invitation_dict = invitation.__dict__
            invitation_dict['created_by'] = invitation.created_by.id

        for key, value in api_invitation.items():
            invitation_value = invitation_dict.get(key)
            if type(invitation_value) == datetime.datetime:
                invitation_value = invitation_value.strftime(
                    '%Y-%m-%dT%H:%M:%S.%f')
            self.assertEqual(invitation_value, value,
                             msg="%s attribute not equal" % key)

    def setUp(self):
        super().setUp()
        user, external_id = self.make_db_user(
            keystone_user_id=base.KEYSTONE_USER_ID)
        # make another invitation not owned by current user
        other_user, external_id = self.make_db_user(
            id=456, keystone_user_id='ks456')

        self.invitation = self.make_invitation(user)
        self.invitation2 = self.make_invitation(other_user, project_id='other')

    def test_invitation_list(self):
        response = self.client.get('/api/v1/invitations/')

        self.assert200(response)
        results = response.get_json().get('results')
        self.assertEqual(1, len(results))
        self.assertInvitationEqual(self.invitation, results[0])

    def test_invitation_list_all_projects(self):
        response = self.client.get('/api/v1/invitations/?all_projects=True')

        self.assert200(response)
        results = response.get_json().get('results')
        self.assertEqual(1, len(results))

    def test_invitation_get(self):
        response = self.client.get('/api/v1/invitations/%s/' %
                                   self.invitation.id)

        self.assert200(response)
        self.assertInvitationEqual(self.invitation, response.get_json())

    def test_invitation_delete(self):
        response = self.client.delete('/api/v1/invitations/%s/' %
                                      self.invitation.id)
        self.assertStatus(response, 204)

    def test_invitation_create(self):
        email = 'new-user@example.org'
        data = {'email': email}
        response = self.client.post('/api/v1/invitations/', json=data)
        self.assertStatus(response, 201)
        api_invitation = response.get_json()
        self.assertEqual(email, api_invitation.get('email'))


class AdminTestInvitationApi(TestInvitationApi):

    ROLES = ['admin']

    def test_invitation_list_all_projects(self):
        response = self.client.get('/api/v1/invitations/?all_projects=True')

        self.assert200(response)
        results = response.get_json().get('results')
        self.assertEqual(2, len(results))

    def test_invitation_get_other(self):
        response = self.client.get('/api/v1/invitations/%s/' %
                                   self.invitation2.id)

        self.assert200(response)
        self.assertInvitationEqual(self.invitation2, response.get_json())

    def test_invitation_create(self):
        # It currently doesn't make sense for an admin to create an invitation
        email = 'new-user@example.org'
        data = {'email': email}
        response = self.client.post('/api/v1/invitations/', json=data)
        self.assert403(response)
