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

import time
from unittest import mock

from oslo_config import cfg

from manuka.tests.functional import base
from manuka.worker import consumer


CONF = cfg.CONF


class TestShibWrapper(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['mail'] = 'test@example.com'
        environ['displayName'] = "john smith"
        environ['persistent-id'] = "1324"
        return self.app(environ, start_response)


class TestViews(base.TestCase):

    def setUp(self):
        super().setUp()
        self.app.wsgi_app = TestShibWrapper(self.app.wsgi_app)

    def test_new_user(self):
        """Given a user who has registered
        And has accepted the terms of service
        When the user visits the site
        Then a keystone user will be created
        And the user will be redirected to the portal with
         a token encoded in the response.
        """
        response = self.client.get('/login/')
        self.assert200(response)
        self.assertTemplateUsed('terms_form.html')

    @mock.patch('manuka.models.keystone_authenticate')
    @mock.patch('manuka.worker.utils.refresh_orcid')
    @mock.patch('manuka.worker.utils.send_welcome_email')
    @mock.patch('manuka.common.clients.get_swift_client')
    @mock.patch('manuka.common.clients.get_admin_nova_client')
    @mock.patch('manuka.common.clients.get_openstack_client')
    @mock.patch('manuka.common.clients.get_admin_keystoneclient')
    def test_agreed_terms_user(self, mock_keystone, mock_openstacksdk,
                               mock_nova, mock_swift, mock_send_email,
                               mock_refresh_orcid,
                               mock_keystone_authenticate):
        """Given a known user who has not registered
        And has just accepted the terms of service
        When the user visits the site
        Then a keystone user will be created
        And the user will be redirected to the portal with
         a token encoded in the response.
        """
        ks_client = mock_keystone.return_value

        mock_user = mock.Mock(id='u123', email='test@example.com')
        mock_user.name = 'test@example.com'
        mock_domain = mock.Mock(id='d123')

        ks_client.users.create.return_value = mock_user
        ks_client.users.update.return_value = mock_user
        ks_client.domains.get.return_value = mock_domain

        token = 'faketoken'
        project_id = 'fake_project_id'
        updated_user = mock_user
        mock_keystone_authenticate.return_value = (token, project_id,
                                                   updated_user)

        with mock.patch('manuka.app.create_app') as mock_create_app:
            mock_create_app.return_value = self.app
            worker = consumer.ConsumerService('fake', CONF)
            worker.run()

            response = self.client.post('/login/', data={'agree': True})
            self.assert200(response)
            self.assertTemplateUsed('creating_account.html')

            # Allow time for the worker to process
            time.sleep(0.1)

            response = self.client.post('/login/')
            self.assertTemplateUsed('redirect.html')
            self.assertContext('token', token)
            self.assertContext('tenant_id', project_id)

            time.sleep(0.1)

            mock_send_email.assert_called_once()
            mock_refresh_orcid.assert_called_once()
            worker.terminate()
