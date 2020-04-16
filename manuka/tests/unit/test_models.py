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

from datetime import datetime

from freezegun import freeze_time
from manuka.extensions import db
from manuka import models
from manuka.tests.unit import base


class TestModels(base.TestCase):
    def setUp(self):
        super().setUp()
        self.shib_attrs = {
            'mail': 'test@example.com',
            'fullname': 'john smith',
            'id': '1324'
        }

    def make_shib_user(self, state='new', agreed_terms=True):
        # create registered user
        shibuser = models.User("1324")
        shibuser.id = "1324"
        shibuser.user_id = 1324
        shibuser.email = "test@example.com"
        shibuser.shibboleth_attributes = self.shib_attrs
        if agreed_terms and state != 'new':
            shibuser.registered_at = datetime.now()
        else:
            shibuser.registered_at = None
        shibuser.state = state
        return shibuser

    def test_create_shibboleth_user(self):
        models.create_shibboleth_user(self.shib_attrs)
        dbuser, = db.session.query(models.User).all()
        self.assertEqual(self.shib_attrs['id'], dbuser.persistent_id)

    @freeze_time("2012-01-14")
    def test_update_shibboleth_user(self):
        # testing classic behavior: handling the mandatory attributes
        user = self.make_shib_user()
        user.displayname = ''
        user.email = ''
        user.shibboleth_attributes = {}
        db.session.add(user)
        db.session.commit()
        models.update_shibboleth_user(user, self.shib_attrs)
        dbuser, = db.session.query(models.User).all()
        self.assertEqual(self.shib_attrs["fullname"], dbuser.displayname)
        self.assertEqual(self.shib_attrs["mail"], dbuser.email)
        self.assertEqual(self.shib_attrs, dbuser.shibboleth_attributes)
        self.assertEqual(datetime(2012, 1, 14), dbuser.last_login)

    def test_update_shibboleth_user_merging(self):
        # testing classic behavior: handling the mandatory attributes
        user = self.make_shib_user()
        user.displayname = ''
        user.email = ''
        user.phone_number = '460 261'
        user.mobile_number = '0401 234 567'
        user.affiliation = 'staff'
        user.orcid = 'pretty'
        user.shibboleth_attributes = {'firstname': 'George',
                                      'surname': 'Cohen',
                                      'orcid': 'ugly'}
        user.shibboleth_attributes.update(self.shib_attrs)
        self.shib_attrs.update({'firstname': ' Godfrey ',
                                'surname': 'Cohen',
                                'telephonenumber': '1800 815 270',
                                'orcid': 'ugly'})
        db.session.add(user)
        db.session.commit()
        models.update_shibboleth_user(user, self.shib_attrs)
        dbuser, = db.session.query(models.User).all()
        self.assertEqual(self.shib_attrs["fullname"], dbuser.displayname)
        self.assertEqual(self.shib_attrs["mail"], dbuser.email)
        self.assertEqual(self.shib_attrs, dbuser.shibboleth_attributes)
        self.assertEqual('Godfrey', dbuser.first_name)
        self.assertEqual('Cohen', dbuser.surname)
        self.assertEqual('1800 815 270', dbuser.phone_number)
        self.assertEqual('0401 234 567', dbuser.mobile_number)
        self.assertEqual('staff', dbuser.affiliation)
        self.assertIsNone(dbuser.home_organization)
        self.assertEqual('pretty', dbuser.orcid)

    def test_update_bad_affiliation(self):
        user = self.make_shib_user()
        self.shib_attrs.update({'affiliation': 'parasite'})
        db.session.add(user)
        db.session.commit()
        models.update_shibboleth_user(user, self.shib_attrs)
        dbuser, = db.session.query(models.User).all()
        self.assertEqual('member', dbuser.affiliation)
        self.assertEqual(self.shib_attrs, dbuser.shibboleth_attributes)

    def test_keystone_authenticate(self):
        pass
