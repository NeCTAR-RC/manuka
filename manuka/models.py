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
import flask

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
    keystone_user_id = db.Column(db.String(64), unique=True)
    displayname = db.Column(db.String(250))
    email = db.Column(db.String(250))
    state = db.Column(db.Enum("new", "registered", "created"))
    registered_at = db.Column(db.DateTime())
    last_login = db.Column(db.DateTime())
    terms_accepted_at = db.Column(db.DateTime())
    terms_version = db.Column(db.String(64))
    ignore_username_not_email = db.Column(db.Boolean())
    first_name = db.Column(db.String(250))
    surname = db.Column(db.String(250))
    phone_number = db.Column(db.String(64))
    mobile_number = db.Column(db.String(64))
    organisation = db.Column(db.String(250))
    orcid = db.Column(db.String(64))
    affiliation = db.Column(db.Enum(*AFFILIATION_VALUES))
    external_ids = db.relationship("ExternalId", back_populates="user",
                                   lazy='joined', cascade="all,delete")
    expiry_status = db.Column(db.String(64))
    expiry_next_step = db.Column(db.DateTime())

    def __init__(self):
        self.state = "new"
        self.active = True

    def __repr__(self):
        return "<Shibboleth User '%d', '%s')>" % (self.id, self.displayname)


class ExternalId(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id))
    user = db.relationship("User", back_populates="external_ids")
    persistent_id = db.Column(db.String(250), unique=True)
    idp = db.Column(db.String(250))
    attributes = db.Column(db.JSON)
    last_login = db.Column(db.DateTime())

    def __init__(self, user, persistent_id, attributes):
        self.user = user
        self.persistent_id = persistent_id
        self.attributes = attributes


def keystone_authenticate(db_user, project_id=None,
                          set_username_as_email=False):
    """Authenticate a user as their default project.
    """
    k_session = keystone.KeystoneSession()
    client = clients.get_admin_keystoneclient(k_session.get_session())
    user = client.users.get(db_user.keystone_user_id)
    domain = client.domains.get(user.domain_id)

    if not user.enabled:
        if db_user.expiry_status:
            db_user.expiry_status = None
            db_user.expiry_next_step = None
            db.session.commit()
            client.users.update(user, enabled=True)
        else:
            flask.abort(401)

    user = sync_keystone_user(client, db_user, user, set_username_as_email)

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


def sync_keystone_user(client, db_user, keystone_user,
                       set_username_as_email=False):
    """Syncs attributes from manuka user -> keystone user
        """
    update_attrs = {}

    if db_user.email != keystone_user.email:
        update_attrs['email'] = db_user.email
    if db_user.displayname != getattr(keystone_user, 'full_name', None):
        update_attrs['full_name'] = db_user.displayname
    if set_username_as_email:
        update_attrs['name'] = db_user.email
    if update_attrs:
        LOG.info("Updating keystone user %s with %s", keystone_user.name,
                 update_attrs)
        keystone_user = client.users.update(keystone_user.id, **update_attrs)
    return keystone_user


def create_db_user(shib_attrs):
    """Create a new user from the Shibboleth attributes

    Required Shibboleth attributes are `id`, `fullname` and `mail`

    Return a newly created user.
    """
    # add db user
    db_user = User()
    external_id = ExternalId(db_user, shib_attrs['id'], shib_attrs)
    external_id.idp = shib_attrs.get('idp')
    db.session.add(db_user)
    db.session.add(external_id)
    db.session.commit()
    return db_user, external_id


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


def _merge_info_values(external_id, shib_attrs, name, current):
    '''Merge non-core user info attributes from 3 sources

    The sources are the attributes provided by the IDP this time
    (in shib_attrs), the attributes provided by the IDP last time
    (in db_user.shibboleth_attributes) and the value from the
    database (current), which may or may not be user supplied.

    Return the normalized and merged value to go into the database
    '''
    shib_current = _normalize(shib_attrs.get(name))
    # (On a new registration, there won't be any previous shib attrs)
    prev_attrs = external_id.attributes or {}
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


def update_db_user(db_user, external_id, shib_attrs):
    """Update a DB User with new details passed from
    Shibboleth.
    """
    db_user.displayname = shib_attrs["fullname"]
    db_user.email = shib_attrs["mail"]
    db_user.first_name = _merge_info_values(external_id, shib_attrs,
                                              'firstname',
                                              db_user.first_name)
    db_user.surname = _merge_info_values(external_id, shib_attrs,
                                           'surname',
                                           db_user.surname)
    db_user.phone_number = _merge_info_values(external_id, shib_attrs,
                                                'telephonenumber',
                                                db_user.phone_number)
    db_user.mobile_number = _merge_info_values(external_id, shib_attrs,
                                                 'mobilenumber',
                                                 db_user.mobile_number)
    db_user.organisation = \
        _merge_info_values(external_id, shib_attrs,
                           'organisation',
                           db_user.organisation)
    db_user.orcid = _merge_info_values(external_id, shib_attrs,
                                         'orcid',
                                         db_user.orcid)
    # Question: do we want to deal with affiliation differently?
    # For example, in the case where the IDP says "member" we
    # want the user to be able to say "staff" or "student" or ...
    db_user.affiliation = _merge_info_values(external_id, shib_attrs,
                                               'affiliation',
                                               db_user.affiliation)
    if db_user.affiliation not in AFFILIATION_VALUES:
        # This could happen if the IDP (real or test) gives us bogus
        # affiliation values.
        LOG.info("Fixed bad affiliation for user %s: '%s' -> '%s'",
                 db_user.displayname, db_user.affiliation, 'member')
        db_user.affiliation = 'member'

    external_id.attributes = shib_attrs

    date_now = datetime.datetime.now()
    db_user.last_login = date_now
    external_id.last_login = date_now
    db.session.commit()
