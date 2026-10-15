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

import collections
import datetime
import flask

from keystoneauth1.identity import v3
from keystoneauth1 import session
from keystoneclient.v3 import client as keystone_client
from oslo_config import cfg
from oslo_log import log
import sqlalchemy_utils
from sqlalchemy_utils.types.encrypted import encrypted_type

from manuka.common import clients
from manuka.common import keystone
from manuka.extensions import db


CONF = cfg.CONF
LOG = log.getLogger(__name__)


AFFILIATION_VALUES = [
    "faculty",
    "student",
    "staff",
    "employee",
    "member",
    "affiliate",
    "alum",
    "library-walk-in",
]

# The login protocols an external identity can come from.
PROTOCOL_SAML = "saml"
PROTOCOL_OIDC = "oidc"
PROTOCOLS = (PROTOCOL_SAML, PROTOCOL_OIDC)

# Identifiers that let a first OpenID Connect login be matched to an
# existing SAML identity, strongest first, as (attribute key, strong).
# Both attribute maps store these under the same keys. subject-id and
# the AAF shared token are not targeted at a particular service and
# are never reassigned, so one match is conclusive. An eppn can be
# reassigned by an institution, so it only counts for an identity that
# logged in recently. Email is deliberately absent: it is neither
# unique nor stable. pairwise-id is targeted at the receiving service
# provider, so the value recorded from Shibboleth never equals the one
# seen through Keycloak; it is stored but cannot match.
AUTO_LINK_KEYS = (
    ("subject-id", True),
    ("shared_token", True),
    ("eppn", False),
)

# Identifiers that must not change between logins of a known subject.
DRIFT_KEYS = ("subject-id", "shared_token")

# Profile attributes that _merge_info_values reconciles between what
# the identity provider sends and what the user may have set.
MERGED_ATTRS = (
    "firstname",
    "surname",
    "telephonenumber",
    "mobilenumber",
    "organisation",
    "affiliation",
)

LinkMatch = collections.namedtuple("LinkMatch", "user key external_id")


def get_key():
    # We need this as a method as key needs to be accessed
    # once config has been initialised
    return CONF.flask.secret_key


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    keystone_user_id = db.Column(db.String(64), unique=True)
    displayname = db.Column(db.String(250))
    email = db.Column(db.String(250))
    state = db.Column(db.Enum("new", "registered", "created", "duplicate"))
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
    orcid_token = db.Column(
        sqlalchemy_utils.StringEncryptedType(
            db.String,
            get_key,
            encrypted_type.AesEngine,
            'pkcs5',
            length=255,
        )
    )
    affiliation = db.Column(db.Enum(*AFFILIATION_VALUES))
    external_ids = db.relationship(
        "ExternalId",
        back_populates="user",
        lazy="joined",
        cascade="all,delete",
    )
    expiry_status = db.Column(db.String(64))
    expiry_next_step = db.Column(db.Date())

    def __init__(self):
        self.state = "new"

    def __repr__(self):
        return f"<User '{self.id}', '{self.displayname}')>"

    def has_protocol(self, protocol):
        """Whether the user has an external identity for a protocol."""
        return any(e.protocol == protocol for e in self.external_ids)


class ExternalId(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey(User.id))
    user = db.relationship("User", back_populates="external_ids")
    persistent_id = db.Column(db.String(250), unique=True)
    idp = db.Column(db.String(250))
    attributes = db.Column(db.JSON)
    last_login = db.Column(db.DateTime())
    protocol = db.Column(
        db.String(32), nullable=False, server_default=PROTOCOL_SAML
    )

    def __init__(
        self, user, persistent_id, attributes, protocol=PROTOCOL_SAML, idp=None
    ):
        if protocol not in PROTOCOLS:
            raise ValueError(f"Unknown login protocol '{protocol}'")
        self.user = user
        self.persistent_id = persistent_id
        self.attributes = attributes
        self.protocol = protocol
        self.idp = idp


class DomainIdpMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    domain_id = db.Column(db.String(36))
    idp_entity_id = db.Column(db.String(250), unique=True)
    last_seen = db.Column(db.DateTime())

    def __init__(self, domain_id, idp_entity_id):
        self.domain_id = domain_id
        self.idp_entity_id = idp_entity_id
        self.last_seen = datetime.datetime.now()


def keystone_authenticate(
    db_user, project_id=None, set_username_as_email=False
):
    """Authenticate a user as their default project."""
    k_session = keystone.KeystoneSession()
    client = clients.get_admin_keystoneclient(k_session.get_session())
    user = client.users.get(db_user.keystone_user_id)
    domain = client.domains.get(user.domain_id)

    if not user.enabled:
        if getattr(user, "inactive", False):
            LOG.info("Activating inactive user %s", db_user.keystone_user_id)
            client.users.update(user, enabled=True, inactive=False)
        else:
            LOG.error("Denying disabled user %s", db_user.keystone_user_id)
            flask.abort(401)

    user = sync_keystone_user(client, db_user, user, set_username_as_email)

    kwargs = {
        "username": user.name,
        "password": CONF.keystone.authenticate_password,
        "auth_url": CONF.keystone.auth_url,
        "user_domain_name": domain.name,
        "project_domain_name": "Default",
    }
    if project_id:
        kwargs["project_id"] = project_id

    user_auth = v3.Password(**kwargs)
    user_session = session.Session(auth=user_auth)
    user_client = keystone_client.Client(session=user_session)

    token = user_client.auth.client.get_token()
    projects = user_client.projects.list(user=user.id)

    return token, projects[0].id, user


def sync_keystone_user(
    client, db_user, keystone_user, set_username_as_email=False
):
    """Syncs attributes from manuka user -> keystone user"""
    update_attrs = {}

    if db_user.email != keystone_user.email:
        update_attrs["email"] = db_user.email
    if db_user.displayname != getattr(keystone_user, "full_name", None):
        update_attrs["full_name"] = db_user.displayname
    if set_username_as_email:
        update_attrs["name"] = db_user.email
    if update_attrs:
        LOG.info(
            "Updating keystone user %s with %s",
            keystone_user.name,
            update_attrs,
        )
        keystone_user = client.users.update(keystone_user.id, **update_attrs)
    return keystone_user


def create_db_user(attrs, protocol=PROTOCOL_SAML):
    """Create a new user from the external attributes

    Required attributes are `id`, `fullname` and `mail`

    Return a newly created user.
    """
    # add db user
    db_user = User()
    external_id = ExternalId(
        db_user, attrs["id"], attrs, protocol=protocol, idp=attrs.get("idp")
    )
    db.session.add(db_user)
    db.session.add(external_id)
    db.session.commit()
    return db_user, external_id


def external_id_attribute_equals(key, value):
    """SQL expression matching rows whose stored attribute equals value.

    Works on the JSON attributes column of both MySQL/MariaDB and the
    SQLite used in tests, including for hyphenated keys.
    """
    return ExternalId.attributes[key].as_string() == value


def find_linkable_user(attrs):
    """Find the existing user an unseen OpenID Connect identity belongs to.

    Walks AUTO_LINK_KEYS, strongest first, and stops at the first key
    present in attrs that matches any SAML identity of a created user.
    Returns a LinkMatch when that key matches exactly one user who has
    no OpenID Connect identity yet, otherwise None. An ambiguous match
    on a key is final: weaker keys are not consulted.
    """
    for key, strong in AUTO_LINK_KEYS:
        value = attrs.get(key)
        if not value:
            continue
        query = (
            db.session.query(ExternalId)
            .join(User, ExternalId.user_id == User.id)
            .filter(ExternalId.protocol == PROTOCOL_SAML)
            .filter(User.state == "created")
            .filter(User.keystone_user_id.isnot(None))
            .filter(external_id_attribute_equals(key, value))
        )
        if not strong:
            max_age = datetime.timedelta(
                days=CONF.oidc.eppn_autolink_max_age_days
            )
            query = query.filter(
                ExternalId.last_login >= datetime.datetime.now() - max_age
            )
        rows = query.all()
        if not rows:
            continue
        by_user = {row.user_id: row for row in rows}
        if len(by_user) > 1:
            LOG.warning(
                "oidc.link.ambiguous: %s matches users %s",
                key,
                sorted(by_user.keys()),
            )
            return None
        external_id = next(iter(by_user.values()))
        user = external_id.user
        if user.has_protocol(PROTOCOL_OIDC):
            LOG.warning(
                "oidc.link.refused: user %s matched by %s already has an "
                "OpenID Connect identity",
                user.id,
                key,
            )
            return None
        return LinkMatch(user, key, external_id)
    return None


def link_external_id(user, attrs, protocol, seed_from=None):
    """Attach a further external identity to an existing user.

    When seed_from, one of the user's existing identities, is given the
    profile attributes it last received are copied onto the new row.
    update_db_user then treats the first login through the new identity
    as a repeat login, keeping values the user set themselves, instead
    of as a provider that is supplying those attributes for the first
    time, which would override them.
    """
    seed = {}
    if seed_from is not None and seed_from.attributes:
        seed = {
            key: value
            for key, value in seed_from.attributes.items()
            if key in MERGED_ATTRS
        }
    external_id = ExternalId(
        user, attrs["id"], seed, protocol=protocol, idp=attrs.get("idp")
    )
    db.session.add(external_id)
    db.session.commit()
    return external_id


def identity_drift(external_id, attrs):
    """The DRIFT_KEYS whose stored value differs from the incoming one.

    A change in an identifier that is never reassigned means the
    provider now presents a different person under the same subject,
    which happens when accounts are merged on the provider side.
    """
    stored = external_id.attributes or {}
    return [
        key
        for key in DRIFT_KEYS
        if stored.get(key) and attrs.get(key) and stored[key] != attrs[key]
    ]


def _normalize(value):
    """Normalize a string

    Removes leading / trailing whitespace and converts empty
    strings to None.

    Return the normalized string.
    """
    if value is None:
        return None
    value = value.strip()
    return value if len(value) > 0 else None


def _merge_info_values(external_id, external_attrs, name, current):
    """Merge non-core user info attributes from 3 sources

    external_id - Existing ExternalID holding attributes from
                  previous login
    external_attrs - Attributes provided by the IDP this session
    name -
    current - value from the DB, which may or may not be user supplied

    Return the normalized and merged value to go into the database
    """
    external_current = _normalize(external_attrs.get(name))
    # (On a new registration, there won't be any previous external attrs)
    prev_attrs = external_id.attributes or {}
    external_previous = _normalize(prev_attrs.get(name))
    current = _normalize(current)
    if external_current is None:
        # Attribute not (or no longer) provided by IDP.  Keep what
        # we had before ... which may be a user-supplied value
        return current
    elif external_previous is None:
        # Attribute was not previously provided by IDP.  Override what
        # the user may have supplied with the new IDP value
        if current and current != external_current:
            LOG.info(
                "IDP overrode attribute %s for user %s: '%s' -> '%s'",
                name,
                external_attrs["fullname"],
                current,
                external_current,
            )
        return external_current
    elif current is None:
        # New attribute which we haven't previously recorded a value for.
        return external_current
    elif external_current == external_previous:
        # Existing IDP supplied attribute that has not changed.  If there
        # is a user override, keep it.
        return current
    else:
        # Existing IDP supplied attribute that has been changed by IDP.
        # Replace user override.
        LOG.info(
            "IDP changed attribute %s for user %s: '%s' -> '%s'",
            name,
            external_attrs["fullname"],
            external_previous,
            external_current,
        )
        return external_current


def update_db_user(db_user, external_id, attrs):
    """Update a DB User with new details passed from
    external auth.
    """
    db_user.displayname = attrs["fullname"]
    db_user.email = attrs["mail"]
    db_user.first_name = _merge_info_values(
        external_id, attrs, "firstname", db_user.first_name
    )
    db_user.surname = _merge_info_values(
        external_id, attrs, "surname", db_user.surname
    )
    db_user.phone_number = _merge_info_values(
        external_id, attrs, "telephonenumber", db_user.phone_number
    )
    db_user.mobile_number = _merge_info_values(
        external_id, attrs, "mobilenumber", db_user.mobile_number
    )
    db_user.organisation = _merge_info_values(
        external_id, attrs, "organisation", db_user.organisation
    )
    # Question: do we want to deal with affiliation differently?
    # For example, in the case where the IDP says "member" we
    # want the user to be able to say "staff" or "student" or ...
    db_user.affiliation = _merge_info_values(
        external_id, attrs, "affiliation", db_user.affiliation
    )
    if db_user.affiliation not in AFFILIATION_VALUES:
        # This could happen if the IDP (real or test) gives us bogus
        # affiliation values.
        LOG.info(
            "Fixed bad affiliation for user %s: '%s' -> '%s'",
            db_user.displayname,
            db_user.affiliation,
            "member",
        )
        db_user.affiliation = "member"

    external_id.attributes = attrs

    date_now = datetime.datetime.now()
    db_user.last_login = date_now
    external_id.last_login = date_now
    # Reset expiry if set
    db_user.expiry_status = None
    db_user.expiry_next_step = None
    db.session.commit()
