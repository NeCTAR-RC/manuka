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
import json
import re
import time
from urllib import parse

import flask
from flask import request
from flask import session
from oslo_config import cfg
from oslo_context import context
from oslo_log import log as logging

from manuka.common import clients
from manuka.extensions import db
from manuka import models
from manuka import oidc
from manuka.worker import api as worker_api


default_bp = flask.Blueprint("default", __name__)
login_bp = flask.Blueprint("login", __name__, url_prefix="/login")
oidc_bp = flask.Blueprint("oidc", __name__, url_prefix="/oidc")

CONF = cfg.CONF
LOG = logging.getLogger(__name__)

# This regex matches an RFC 5322 addr-spec with a 2 to 4 char TLD
EMAIL_RE = re.compile(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)")

# Attributes every login protocol must supply before a user can be
# matched or created.
REQUIRED_ATTRS = ("id", "mail", "fullname")

SAML_LOGOUT_URL = "/Shibboleth.sso/Logout?return=http://nectar.org.au/"

# The explanation shown on the error page when a login protocol does
# not supply the required attributes, keyed by protocol.
MISSING_ATTR_MSG = {
    "saml": [
        "Not enough details have been received from your "
        "institution to allow you to log on to the cloud. We "
        "need your id, your e-mail and your full name.",
        "Please contact your institution and tell them that "
        'their "AAF IdP" is broken!',
        "Copy and paste the details below into your email to "
        "your institution's support desk.",
        "The following required fields are missing or incorrect "
        "from the AAF service:",
    ],
    "oidc": [
        "Not enough details have been received from the login service "
        "to allow you to log on to the cloud. We need your id, your "
        "e-mail and your full name.",
        "Your institution may not release these details, or the login "
        "service may be misconfigured. Please contact support and "
        "include the details below.",
        "The following required fields are missing or incorrect:",
    ],
}

# Session keys that only live for the duration of one OIDC login.
OIDC_SESSION_KEYS = ("oidc_attrs", "oidc_attrs_exp", "oidc_return_path")
# Authlib keeps the state, nonce and PKCE verifier of each started
# login under keys with this prefix.
AUTHLIB_STATE_PREFIX = f"_state_{oidc.CLIENT_NAME}_"


class AttrMap:
    """Map attributes from an external identity source to manuka's names.

    Subclasses set ``data`` to a dict of source attribute name to
    manuka attribute name and ``EMAIL_KEY`` to the source name of the
    email attribute, which is normalised to lower case.
    """

    data = {}
    EMAIL_KEY = "mail"

    @classmethod
    def parse(cls, source):
        metadata = {}
        for k, v in cls.data.items():
            value = source.get(k)
            if not value:
                continue
            if isinstance(value, (list, tuple)):
                # Multi-valued attributes are joined the way mod_shib
                # joins them so stored attributes keep one shape.
                value = ";".join(str(item) for item in value)
            if k == cls.EMAIL_KEY:
                value = value.lower()
            metadata[v] = value
        return metadata

    @classmethod
    def get_attr(cls, name):
        for k, v in cls.data.items():
            if name == v:
                return k


class ShibbolethAttrMap(AttrMap):
    EMAIL_KEY = "mail"
    data = {
        "persistent-id": "id",
        "cn": "cn",
        "displayName": "fullname",
        "givenName": "firstname",
        "sn": "surname",
        "uid": "uid",
        "mail": "mail",
        "eppn": "eppn",
        "l": "location",
        "description": "description",
        "o": "organisation",
        "affiliation": "affiliation",
        "unscoped-affiliation": "unscoped-affiliation",
        "assurance": "assurance",
        "Shib-Identity-Provider": "idp",
        "shared-token": "shared_token",
        "homeOrganization": "homeorganization",
        "homeOrganizationType": "homeorganizationtype",
        "telephoneNumber": "telephonenumber",
        "mobileNumber": "mobilenumber",
        "eduPersonOrcid": "orcid",
        "subject-id": "subject-id",
        "pairwise-id": "pairwise-id",
    }


class OIDCAttrMap(AttrMap):
    """Claims from the OpenID Connect provider.

    The claim names are set by the protocol mappers on the provider's
    client configuration. The manuka names match what ShibbolethAttrMap
    produces, so identities from both protocols compare like for like.
    """

    EMAIL_KEY = "email"
    data = {
        "sub": "id",
        "iss": "idp",
        "email": "mail",
        "name": "fullname",
        "given_name": "firstname",
        "family_name": "surname",
        "preferred_username": "uid",
        "eduperson_principal_name": "eppn",
        "au_edu_person_shared_token": "shared_token",
        "subject_id": "subject-id",
        "pairwise_id": "pairwise-id",
        "eduperson_affiliation": "affiliation",
        "eduperson_scoped_affiliation": "scoped_affiliation",
        "schac_home_organization": "homeorganization",
        "eduperson_orcid": "orcid",
        "phone_number": "telephonenumber",
        # The alias of the identity provider that brokered the login
        # (for example aaf or tuakiri), not an entityID.
        "identity_provider": "federation",
    }


def _check_required_attrs(attrs, attr_map, protocol):
    """Check the attributes needed to identify and register a user.

    Returns a dict of field name to error message, empty when the
    attributes are acceptable.
    """
    errors = {}
    for field in REQUIRED_ATTRS:
        if field not in attrs:
            errors[field] = (
                f"Required field '{attr_map.get_attr(field)}' can't be found."
            )

    if errors:
        LOG.error(
            "The %s identity provider is not returning the required "
            "attributes. The following are missing: %s. "
            "The following are present: %s.",
            protocol,
            ", ".join(errors.keys()),
            attrs,
        )

    mail_value = attrs.get("mail")
    if mail_value and not EMAIL_RE.match(mail_value):
        LOG.error(
            "The %s identity provider is returning a bad 'mail' "
            "attribute: '%s'",
            protocol,
            mail_value,
        )
        errors["mail"] = (
            "The '{}' field must be one RFC 5322 <addr-spec>: "
            "the value provided is '{}'".format(
                attr_map.get_attr("mail"), mail_value
            )
        )
    return errors


def _render_attr_errors(errors, protocol):
    """Render the error page for missing or invalid login attributes."""
    data = {
        "title": "Error",
        "message": MISSING_ATTR_MSG[protocol],
        "errors": sorted(errors.values()),
    }
    if protocol == models.PROTOCOL_OIDC:
        data["support_url"] = CONF.support_url
    return flask.render_template("error.html", **data)


def _validate_return_path(value):
    """Validate a requested return-path against the allow list.

    Returns a ``(target, error_response)`` pair. ``target`` is the
    configured default target when no return-path was requested, the
    requested path when it is in the allow list, and ``None`` with a rendered
    error page when it is blocked.
    """
    if not value:
        return CONF.default_target, None

    url_pieces = parse.urlparse(value)
    url_match = f"{url_pieces.scheme}://{url_pieces.netloc}{url_pieces.path}"
    if url_match in (CONF.allow_list or []):
        return value, None
    if CONF.allow_any_return_path:
        LOG.warning("Allowing return-path %s outside the allow list", value)
        return value, None

    LOG.warning("Attempt to authenticate to a blocked URL: %s", value)
    data = {
        "title": "Authentication Error",
        "message": f"You attempted to authenticate to the {value} "
        "URL, which is not permitted by this service.",
    }
    return None, flask.render_template("error.html", **data)


def _logout_url(protocol):
    """The URL that ends the login session for the given protocol."""
    if protocol == models.PROTOCOL_OIDC:
        return flask.url_for("oidc.oidc_logout")
    return SAML_LOGOUT_URL


def _set_session_identity(external_id):
    """Record the identity that has just authenticated in the session."""
    session["external_id"] = external_id.id
    session["auth_time"] = int(time.time())
    session.pop("shib_user_id", None)


def _current_external_id():
    """The ExternalId row for the identity in the current session.

    Aborts with 404 when the session holds no known identity.
    """
    external_id = None
    row_id = session.get("external_id")
    if row_id is not None:
        external_id = db.session.get(models.ExternalId, row_id)
    elif session.get("shib_user_id"):
        # Sessions established before the external_id key existed.
        # Remove this fallback once every such session has expired.
        external_id = (
            db.session.query(models.ExternalId)
            .filter_by(persistent_id=session["shib_user_id"])
            .first()
        )
    if external_id is None:
        flask.abort(404)
    return external_id


def _complete_login(db_user, external_id, attrs, protocol):
    """Finish a login once the user has been identified.

    Handles terms acceptance, account creation progress, username
    changes and the final hand-off of a keystone token to the
    requested target. Shared by every login protocol.
    """
    current_terms_version = CONF.terms_version

    if request.form.get("agree") and db_user.state == "new":
        date_now = datetime.datetime.now()
        db_user.registered_at = date_now
        db_user.terms_accepted_at = date_now
        db_user.state = "registered"
        db_user.terms_version = current_terms_version
        models.update_db_user(db_user, external_id, attrs)
        db.session.commit()
        LOG.info("User %s accepted terms", db_user)
        # after registering present the user with a page indicating
        # there account is being created
        worker = worker_api.WorkerAPI()
        ctxt = context.RequestContext()
        worker.create_user(ctxt, attrs)

    if request.form.get("agree") and db_user.state == "created":
        # New terms version accepted
        db_user.terms_version = current_terms_version
        db_user.terms_accepted_at = datetime.datetime.now()
        models.update_db_user(db_user, external_id, attrs)
        db.session.commit()
        LOG.info("User %s accepted new terms", db_user)

    if request.form.get("ignore_username"):
        # Ignore different username
        db_user.ignore_username_not_email = True
        db.session.commit()
        LOG.info("User %s ignoring username not email", db_user)

    if db_user.terms_version != current_terms_version:
        LOG.info("User %s terms version not current", db_user)
        data = {
            "title": "Terms and Conditions.",
            "terms_version": current_terms_version,
            "updated_terms": db_user.terms_version,
            "logout_url": _logout_url(protocol),
        }
        return flask.render_template("terms_form.html", **data)

    if db_user.state in ("registered", "duplicate"):
        LOG.info("User %s in registered or duplicate state", db_user)
        data = {
            "title": "Creating Account...",
            "support_url": CONF.support_url,
        }
        return flask.render_template("creating_account.html", **data)

    if db_user.state == "created":
        set_username_as_email = False

        if request.form.get("change_username"):
            # User wants to change their username to match email
            set_username_as_email = True
            LOG.info("User %s changing username to match email", db_user)

        try:
            token, project_id, user = models.keystone_authenticate(
                db_user, set_username_as_email=set_username_as_email
            )
        except Exception as e:
            # TODO(russell) the error handing this exception is
            # to broad.

            # Martin: the error is occurring because Keystone has no
            # knowledge of the user, but we (fakeshib) do...  Which
            # raises an interesting philosophical question - how did
            # we get into this state?  BTW, if the user is in this
            # state, he has lost everything in the cloud, and is
            # likely to be unhappy...
            LOG.exception(
                "A user known to manuka isn't known by "
                "Keystone! Their user id is: %s",
                db_user.keystone_user_id,
            )
            data = {
                "title": "Error",
                "message": [
                    "Your details could not be found on the central "
                    "authentication server. Thus you will not be able "
                    "to access the cloud!",
                    "The error message is:",
                ],
                "errors": [str(e)],
                "support_url": CONF.support_url,
            }

            # We should perhaps redirect the user to a nicer more
            # useful error page...
            return flask.render_template("error.html", **data)

    models.update_db_user(db_user, external_id, attrs)

    if user.name != user.email and not db_user.ignore_username_not_email:
        LOG.info("User %s username and email do not match", db_user)
        data = {"user": user}
        return flask.render_template("username_form.html", **data)

    # sjjf: default to the configured target URL, but allow the source
    # to specify a different return-path. The specified return path is
    # then verified against an allow list.
    target, error_response = _validate_return_path(
        request.args.get("return-path")
    )
    if error_response is not None:
        return error_response

    data = {"token": token, "tenant_id": project_id, "target": target}

    return flask.render_template("redirect.html", **data)


@default_bp.route("/account_status")
def account_status():
    external_id = _current_external_id()
    data = {"state": external_id.user.state}
    return json.dumps(data)


# The old path is under the Shibboleth protected /login location, which
# OIDC logins cannot reach. Keep it for pages loaded before the move.
login_bp.add_url_rule("/account_status", "account_status", account_status)


@login_bp.route("/", methods=("GET", "POST"))
def root():
    attrs = ShibbolethAttrMap.parse(request.environ)
    LOG.info("SAML attributes received: %s.", attrs)
    errors = _check_required_attrs(attrs, ShibbolethAttrMap, "saml")
    if errors:
        return _render_attr_errors(errors, "saml")

    external_id = (
        db.session.query(models.ExternalId)
        .filter_by(persistent_id=attrs["id"])
        .first()
    )
    if not external_id:
        db_user, external_id = models.create_db_user(attrs)
    else:
        db_user = external_id.user

    _set_session_identity(external_id)

    return _complete_login(db_user, external_id, attrs, "saml")


@oidc_bp.before_request
def _oidc_enabled():
    if not CONF.oidc.enabled:
        flask.abort(404)


def _oidc_redirect_url():
    """The callback URL registered with the provider."""
    if CONF.oidc.redirect_url:
        return CONF.oidc.redirect_url
    return flask.url_for("oidc.oidc_callback", _external=True)


def _clear_oidc_session():
    """Drop the state of any earlier OIDC login from the session."""
    for key in OIDC_SESSION_KEYS:
        session.pop(key, None)
    for key in [k for k in session if k.startswith(AUTHLIB_STATE_PREFIX)]:
        session.pop(key, None)


def _session_oidc_attrs():
    """The attributes of the OIDC login in progress, or None."""
    attrs = session.get("oidc_attrs")
    expires = session.get("oidc_attrs_exp") or 0
    if not attrs or time.time() > expires:
        session.pop("oidc_attrs", None)
        session.pop("oidc_attrs_exp", None)
        return None
    return attrs


def _return_path_args(return_path=None):
    """The query arguments that carry the return-path to the next page."""
    if return_path is None:
        return_path = request.args.get("return-path")
    return {"return-path": return_path} if return_path else {}


def _render_login_failed(detail):
    data = {
        "title": "Login failed",
        "message": [
            "We could not complete your login with the login service.",
            "The error was:",
        ],
        "errors": [detail],
        "support_url": CONF.support_url,
    }
    return flask.render_template("error.html", **data)


def _render_identity_drift():
    data = {
        "title": "Login blocked",
        "message": [
            "The identity your institution provided does not match the "
            "one previously connected to this login.",
            "To protect your account we have not logged you in.",
        ],
        "support_url": CONF.support_url,
    }
    return flask.render_template("error.html", **data)


def _render_choose_link(attrs):
    """Ask a first-time OIDC user whether they already have an account."""
    existing = (
        db.session.query(models.User)
        .filter_by(email=attrs["mail"], state="created")
        .first()
    )
    data = {
        "title": "Welcome to the Nectar Research Cloud",
        "attrs": attrs,
        "email_known": existing is not None,
    }
    return flask.render_template("choose_link.html", **data)


@oidc_bp.route("/login/")
def oidc_login():
    """Start a login with the OpenID Connect provider.

    The return-path is validated before the browser leaves the site
    and carried in the session until the provider sends it back.
    """
    return_path = request.args.get("return-path")
    target, error_response = _validate_return_path(return_path)
    if error_response is not None:
        return error_response

    _clear_oidc_session()
    if return_path:
        session["oidc_return_path"] = return_path
    client = oidc.get_client()
    return client.authorize_redirect(_oidc_redirect_url())


@oidc_bp.route("/callback")
def oidc_callback():
    """Exchange the provider's code for the user's identity claims.

    Nothing is rendered here. The code and state in this URL are single
    use, so the pages that follow are served from /oidc/continue/,
    which the browser can reload and post forms to.
    """
    error = request.args.get("error")
    if error:
        detail = request.args.get("error_description") or error
        LOG.warning("oidc.callback.error: provider returned %s", detail)
        return _render_login_failed(detail)

    client = oidc.get_client()
    try:
        token = client.authorize_access_token()
        claims = oidc.fetch_claims(client, token)
    except (oidc.ProviderError, oidc.OIDCError) as e:
        LOG.warning("oidc.callback.error: %s", e)
        return _render_login_failed(str(e))

    attrs = OIDCAttrMap.parse(claims)
    LOG.info("OIDC attributes received: %s.", attrs)
    errors = _check_required_attrs(attrs, OIDCAttrMap, models.PROTOCOL_OIDC)
    if errors:
        return _render_attr_errors(errors, models.PROTOCOL_OIDC)

    session["oidc_attrs"] = attrs
    session["oidc_attrs_exp"] = int(time.time()) + CONF.oidc.session_timeout
    return_path = session.pop("oidc_return_path", None)
    return flask.redirect(
        flask.url_for("oidc.oidc_continue", **_return_path_args(return_path))
    )


@oidc_bp.route("/continue/", methods=("GET", "POST"))
def oidc_continue():
    """Finish an OpenID Connect login.

    Serves every page after the provider callback: the choice between
    linking an existing account and creating a new one, the terms,
    the account creation progress page, the username check and the
    final hand-off to the dashboard.
    """
    attrs = _session_oidc_attrs()
    if attrs is None:
        return flask.redirect(
            flask.url_for("oidc.oidc_login", **_return_path_args())
        )

    external_id = (
        db.session.query(models.ExternalId)
        .filter_by(persistent_id=attrs["id"], protocol=models.PROTOCOL_OIDC)
        .first()
    )
    if external_id is not None:
        db_user = external_id.user
        drift = models.identity_drift(external_id, attrs)
        if drift:
            LOG.warning(
                "oidc.identity_drift: subject %s of user %s now carries a "
                "different %s",
                attrs["id"],
                db_user.id,
                ", ".join(drift),
            )
            if CONF.oidc.deny_on_identity_drift:
                return _render_identity_drift()
    else:
        match = models.find_linkable_user(attrs)
        if match is not None:
            db_user = match.user
            external_id = models.link_external_id(
                db_user,
                attrs,
                models.PROTOCOL_OIDC,
                seed_from=match.external_id,
            )
            LOG.info(
                "oidc.autolink: subject %s linked to user %s (keystone %s) "
                "by %s of external id %s",
                attrs["id"],
                db_user.id,
                db_user.keystone_user_id,
                match.key,
                match.external_id.id,
            )
        elif not request.form.get("create_new"):
            return _render_choose_link(attrs)
        else:
            db_user, external_id = models.create_db_user(
                attrs, protocol=models.PROTOCOL_OIDC
            )
            LOG.info(
                "oidc.newuser: created user %s for subject %s",
                db_user.id,
                attrs["id"],
            )

    _set_session_identity(external_id)
    return _complete_login(db_user, external_id, attrs, models.PROTOCOL_OIDC)


@oidc_bp.route("/logout/")
def oidc_logout():
    """End the manuka session and the provider's single sign-on session."""
    session.clear()
    post_logout_url = CONF.oidc.post_logout_redirect_url
    client = oidc.get_client()
    metadata = client.load_server_metadata() if client else {}
    end_session_url = metadata.get("end_session_endpoint")
    if not end_session_url:
        return flask.redirect(post_logout_url)
    params = {
        "client_id": CONF.oidc.client_id,
        "post_logout_redirect_uri": post_logout_url,
    }
    return flask.redirect(f"{end_session_url}?{parse.urlencode(params)}")


@default_bp.route("/terms.html")
def terms():
    template = f"{CONF.terms_version}-terms_text.html"
    return flask.render_template(template)


@default_bp.route("/")
def default_redirect():
    return flask.redirect("/login/", code=301)


@default_bp.route("/orcid/link/")
def orcid_link():
    code = request.args.get("code")
    redirect_url = request.args.get("next", None)

    if not code:
        data = {
            "title": "Error",
            "message": "Invalid Request",
        }
        return flask.render_template("error.html", **data), 400
    external_id = _current_external_id()
    orcid_client = clients.get_orcid_client()
    try:
        oauth_redirect_url = request.base_url
        # This is a workaround for orcid dropping the value of our next arg from redirect url
        # https://host/?next=https://anotherhost -> https://host/?next&code=XYZ
        if redirect_url is not None:
            oauth_redirect_url += '?next'
            if redirect_url:
                oauth_redirect_url += f'={redirect_url}'
        data = orcid_client.get_token_from_authorization_code(
            code, oauth_redirect_url
        )
    except Exception as e:
        LOG.error("Failed to get orcid token")
        LOG.exception(e)
    else:
        user = external_id.user
        user.orcid = data.get('orcid')
        user.orcid_token = data.get('access_token')
        db.session.add(user)
        db.session.commit()

    if not redirect_url:
        redirect_url = CONF.orcid.default_redirect_url
    return flask.redirect(redirect_url)


@default_bp.route("/orcid/unlink/", methods=["POST"])
def orcid_unlink():
    redirect_url = request.form.get("next")
    if not redirect_url:
        data = {
            "title": "Error",
            "message": "Invalid Request",
        }
        return flask.render_template("error.html", **data), 400
    external_id = _current_external_id()
    user = external_id.user
    user.orcid = None
    user.orcid_token = None
    db.session.add(user)
    db.session.commit()

    return flask.redirect(redirect_url)
