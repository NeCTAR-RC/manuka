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

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client as keystone_client
from oslo_config import cfg
from oslo_log import log

from manuka.common import clients
from manuka.common import keystone
from manuka.extensions import db

CONF = cfg.CONF
LOG = log.getLogger(__name__)


AFFILIATION_VALUES = ["faculty", "student", "staff",
                      "employee", "member", "affiliate",
                      "alum", "library-walk-in"]


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    persistent_id = db.Column(db.String(250), unique=True)
    user_id = db.Column(db.String(64))
    displayname = db.Column(db.String(250))
    email = db.Column(db.String(250))
    state = db.Column(db.Enum("new", "registered", "created"))
    registered_at = db.Column(db.DateTime())
    last_login = db.Column(db.DateTime())
    terms_accepted_at = db.Column(db.DateTime())
    terms_version = db.Column(db.String(64))
    # Hard-wiring the pickle protocol avoids version problems when rcshib
    # and dashboard instances running different versions of Python with
    # different default pickle protocols update the shibboleth attributes.
    # We could treat this as transitional, but the problem may arise again,
    # but permanent hard-wiring avoids recurrences of the problem.  (Unless
    # protocol 2 is deprecated.  But we can handle that by bumping up the
    # hard-wired protocol, and doing a migration to convert the pickles.)
    shibboleth_attributes = db.Column(db.PickleType(protocol=2))
    ignore_username_not_email = db.Column(db.Boolean())
    first_name = db.Column(db.String(250))
    surname = db.Column(db.String(250))
    phone_number = db.Column(db.String(64))
    mobile_number = db.Column(db.String(64))
    home_organization = db.Column(db.String(250))
    orcid = db.Column(db.String(64))
    affiliation = db.Column(db.Enum(*AFFILIATION_VALUES))

    def __init__(self, persistent_id):
        self.persistent_id = persistent_id
        self.state = "new"

    def __repr__(self):
        return "<Shibboleth User '%d', '%s')>" % (self.id, self.displayname)


def keystone_authenticate(user_id, project_id=None, email=None,
                          full_name=None, set_username_as_email=False):
    """Authenticate a user as their default project.
    """
    k_session = keystone.KeystoneSession()
    client = clients.get_admin_keystoneclient(k_session.get_session())
    user = client.users.get(user_id)
    domain = client.domains.get(user.domain_id)
    update_attrs = {}
    if (email and email != user.email):
        update_attrs['email'] = email
    if full_name and full_name != getattr(user, 'full_name', None):
        update_attrs['full_name'] = full_name
    if set_username_as_email:
        update_attrs['name'] = update_attrs.get('email', user.email)
    if update_attrs:
        LOG.info("Updating user %s with %s", user.name, update_attrs)
        user = keystone.users.update(user_id, **update_attrs)

    kwargs = {'username': user.name,
              'password': CONF.keystone.authenticate_password,
              'auth_url': CONF.keystone.auth_url,
              'user_domain_name': domain.name,
              'project_domain_name': 'Default'}
    if project_id:
        kwargs['project_id'] = project_id

    user_auth = v3.Password(**kwargs)
    user_session = session.Session(auth=user_auth)
    user_client = keystone_client.Client(session=user_session)

    token = user_client.auth.client.get_token()
    projects = user_client.projects.list(user=user.id)
    return token, projects[0].id, user


def create_shibboleth_user(shib_attrs):
    """Create a new user from the Shibboleth attributes

    Required Shibboleth attributes are `id`, `fullname` and `mail`

    Return a newly created user.
    """
    # add shibboleth user
    shibuser = User(shib_attrs["id"])
    db.session.add(shibuser)
    db.session.commit()
    return shibuser


def _normalize(value):
    '''Normalize a string

    Removes leading / trailing whitespace and converts empty
    strings to None.

    Return the normalized string.
    '''
    if value is None:
        return None
    value = value.strip()
    return value if len(value) > 0 else None


def _merge_info_values(shib_user, shib_attrs, name, current):
    '''Merge non-core user info attributes from 3 sources

    The sources are the attributes provided by the IDP this time
    (in shib_attrs), the attributes provided by the IDP last time
    (in shib_user.shibboleth_attributes) and the value from the
    database (current), which may or may not be user supplied.

    Return the normalized and merged value to go into the database
    '''
    shib_current = _normalize(shib_attrs.get(name))
    # (On a new registration, there won't be any previous shib attrs)
    prev_attrs = shib_user.shibboleth_attributes or {}
    shib_previous = _normalize(prev_attrs.get(name))
    current = _normalize(current)
    if shib_current is None:
        # Attribute not (or no longer) provided by IDP.  Keep what
        # we had before ... which may be a user-supplied value
        return current
    elif shib_previous is None:
        # Attribute was not previously provided by IDP.  Override what
        # the user may have supplied with the new IDP value
        if current and current != shib_current:
            LOG.info("IDP overrode attribute %s for user %s: '%s' -> '%s'",
                     name, shib_attrs['fullname'], current, shib_current)
        return shib_current
    elif current is None:
        # New attribute which we haven't previously recorded a value for.
        return shib_current
    elif shib_current == shib_previous:
        # Existing IDP supplied attribute that has not changed.  If there
        # is a user override, keep it.
        return current
    else:
        # Existing IDP supplied attribute that has been changed by IDP.
        # Replace user override.
        LOG.info("IDP changed attribute %s for user %s: '%s' -> '%s'",
                 name, shib_attrs['fullname'], shib_previous, shib_current)
        return shib_current


def update_shibboleth_user(shib_user, shib_attrs):
    """Update a Shibboleth User with new details passed from
    Shibboleth.
    """
    shib_user.displayname = shib_attrs["fullname"]
    shib_user.email = shib_attrs["mail"]
    shib_user.first_name = _merge_info_values(shib_user, shib_attrs,
                                              'firstname',
                                              shib_user.first_name)
    shib_user.surname = _merge_info_values(shib_user, shib_attrs,
                                           'surname',
                                           shib_user.surname)
    shib_user.phone_number = _merge_info_values(shib_user, shib_attrs,
                                                'telephonenumber',
                                                shib_user.phone_number)
    shib_user.mobile_number = _merge_info_values(shib_user, shib_attrs,
                                                 'mobilenumber',
                                                 shib_user.mobile_number)
    shib_user.home_organization = \
        _merge_info_values(shib_user, shib_attrs,
                           'organisation',
                           shib_user.home_organization)
    shib_user.orcid = _merge_info_values(shib_user, shib_attrs,
                                         'orcid',
                                         shib_user.orcid)
    # Question: do we want to deal with affiliation differently?
    # For example, in the case where the IDP says "member" we
    # want the user to be able to say "staff" or "student" or ...
    shib_user.affiliation = _merge_info_values(shib_user, shib_attrs,
                                               'affiliation',
                                               shib_user.affiliation)
    if shib_user.affiliation not in AFFILIATION_VALUES:
        # This could happen if the IDP (real or test) gives us bogus
        # affiliation values.
        LOG.info("Fixed bad affiliation for user %s: '%s' -> '%s'",
                 shib_user.displayname, shib_user.affiliation, 'member')
        shib_user.affiliation = 'member'

    shib_user.shibboleth_attributes = shib_attrs

    date_now = datetime.datetime.now()
    shib_user.last_login = date_now
    db.session.commit()
