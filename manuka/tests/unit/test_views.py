from datetime import datetime
from oslo_config import cfg
import shutil
import tempfile
from unittest import mock

from manuka import models
from manuka import views
from manuka.tests.unit import base
from manuka.extensions import db


CONF = cfg.CONF


class MockIdentityService(object):
    def __init__(self, token):
        self.token = token

    def authenticate_shibboleth(self, id, project_id):
        return self.token


class TestShibbolethAttrMap(base.TestCase):
    def test_parse(self):
        environ = {"persistent-id": "1234",
                   "mail": "Test@example.com"}
        self.assertEqual(views.ShibbolethAttrMap.parse(environ),
                         {'id': '1234', 'mail': 'test@example.com'})

    def test_attr(self):
        self.assertEqual(views.ShibbolethAttrMap.get_attr("mail"),
                         "mail")
        self.assertEqual(views.ShibbolethAttrMap.get_attr("location"),
                         "l")


class TestShibWrapper(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['mail'] = 'test@example.com'
        environ['displayName'] = "john smith"
        environ['persistent-id'] = "1324"
        return self.app(environ, start_response)


@mock.patch('manuka.views.worker_api', new=mock.Mock())
class TestRoot(base.TestCase):
    missing_attr_msg = "Not enough details have been received from " \
                       "your institution to allow you to " \
                       "log on to the cloud. We need your id, your " \
                       "e-mail and your full name.<br />" \
                       "Please contact your institution and tell " \
                       "them that their \"AAF IdP\" is broken!<br />" \
                       "Copy and paste the details below into your email to " \
                       "your institution's support desk.<br />" \
                       "<b>The following required fields are missing " \
                       "from the AAF service:</b>"

    def make_shib_user(self, state='new', agreed_terms=True):
        # create registered user
        shibuser = models.User("1324")
        shibuser.id = 1324
        shibuser.user_id = 1324
        shibuser.email = "test@example.com"
        shibuser.shibboleth_attributes = {
            'mail': 'test@example.com',
            'fullname': 'john smith',
            'id': '1324'
        }
        if agreed_terms and state != 'new':
            date_now = datetime.now()
            shibuser.registered_at = date_now
            shibuser.terms_accepted_at = date_now
            shibuser.terms_version = 'v1'
        else:
            shibuser.registered_at = None
            shibuser.terms_accepted_at = None
            shibuser.terms_version = None
        shibuser.state = state
        shibuser.ignore_username_not_email = False
        return shibuser

    def setUp(self):
        super().setUp()
        self.app.wsgi_app = TestShibWrapper(self.app.wsgi_app)
        self.tmp_dir = tempfile.mkdtemp()
        self.default_config = {
            'terms_version': 'v1',
            'support_url': 'http://support',
            'target': 'http://dashboard'
        }

    def tearDown(self):
        shutil.rmtree(self.tmp_dir)

    @mock.patch("manuka.models.create_shibboleth_user")
    def test_new_user(self, mock_create):
        """Given a user who has registered
        And has accepted the terms of service
        When the user visits the site
        Then a keystone user will be created
        And the user will be redirected to the portal with
         a token encoded in the response.
        """
        # mock user
        user = self.make_shib_user(state='new', agreed_terms=False)
        mock_create.return_value = user

        response = self.client.get('/')
        self.assert200(response)
        self.assertTemplateUsed('terms_form.html')

    @mock.patch("manuka.models.create_shibboleth_user")
    @mock.patch("manuka.models.update_shibboleth_user")
    def test_agreed_terms_user(self,
                               mock_update,
                               mock_create):
        """Given a known user who has not registered
        And has just accepted the terms of service
        When the user visits the site
        Then a keystone user will be created
        And the user will be redirected to the portal with
         a token encoded in the response.
        """

        # mock user
        user = self.make_shib_user(state='new')
        mock_create.return_value = user

        # mock token
        token_string = '{"access": {"serviceCatalog": ' \
            '[], "token": {"id": "aaaaaa"}}}'
        token = mock.Mock()
        token.to_json.return_value = token_string
        # mock_identity_service.return_value = mock.MockIdentityService(token)

        response = self.client.post('/', data={'agree': True})

        # confirm that the keystone user was created
        mock_update.assert_called_once_with(
            db, user, {'mail': 'test@example.com',
                       'fullname': 'john smith', 'id': '1324'})

        self.assertEqual(user.state, "registered")
        self.assert200(response)
        self.assertTemplateUsed('creating_account.html')

    def test_registered_user(self):
        """Given a user who has registered
        And has accepted the terms of service
        When the user visits the site
        Then a keystone user will be created
        And the user will be redirected to the portal with
         a token encoded in the response.
        """
        shibuser = self.make_shib_user(state='registered')
        db.session.add(shibuser)
        db.session.commit()
        response = self.client.get('/')
        self.assert200(response)
        self.assertTemplateUsed('creating_account.html')

    @mock.patch("manuka.models.create_shibboleth_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_created_user(self,
                          mock_keystone_authenticate,
                          mock_create):
        """Given a known user who has already has a keystone account
        When the user visits the site
        And the user will be redirected to the portal with
         a token encoded in the response.
        """
        db.session.add(self.make_shib_user(state='created'))
        db.session.commit()

        # mock token
        token = "secret"
        project_id = 'abcdef'
        user = mock.Mock()
        user.configure_mock(name="test@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.get('/')

        self.assert200(response)
        self.assertTemplateUsed('redirect.html')
        self.assertContext('tenant_id', project_id)
        self.assertContext('token', token)
        self.assertContext('target', CONF.default_target)

    @mock.patch("manuka.models.create_shibboleth_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_email_changed(self,
                           mock_keystone_authenticate,
                           mock_create):
        """Given a known user who's username is different to email

        User will be shown a form asking if they would like to
        change username
        """
        db.session.add(self.make_shib_user(state='created'))
        db.session.commit()

        # mock token
        token = "secret"
        project_id = 'abcdef'
        user = mock.Mock()
        user.configure_mock(name="foo@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.get('/')
        mock_keystone_authenticate.assert_called_once_with(
            '1324', email=u'test@example.com', full_name=None,
            set_username_as_email=False)

        # confirm that the redirect is passed correctly
        self.assert200(response)
        self.assertTemplateUsed('username_form.html')

    @mock.patch("manuka.models.create_shibboleth_user")
    @mock.patch("manuka.models.keystone_authenticate")
    def test_email_changed_ignored(self,
                                   mock_keystone_authenticate,
                                   mock_create):
        """Given a known user who's username is different to email

        User will be logged in as they ignored different email
        """
        db.session.add(self.make_shib_user(state='created'))
        db.session.commit()

        # mock token
        token = "secret"
        project_id = 'abcdef'
        user = mock.Mock()
        user.configure_mock(name="foo@example.com", email="test@example.com")
        mock_keystone_authenticate.return_value = token, project_id, user

        response = self.client.post('/', data={'ignore_username': True})

        self.assert200(response)
        self.assertTemplateUsed('redirect.html')
        self.assertContext('tenant_id', project_id)
        self.assertContext('token', token)
        self.assertContext('target', CONF.default_target)
