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
from manuka.worker import api as worker_api


default_bp = flask.Blueprint("default", __name__)
login_bp = flask.Blueprint("login", __name__, url_prefix="/login")

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
}


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

    LOG.warning("Attempt to authenticate to a blocked URL: %s", value)
    data = {
        "title": "Authentication Error",
        "message": f"You attempted to authenticate to the {value} "
        "URL, which is not permitted by this service.",
    }
    return None, flask.render_template("error.html", **data)


def _logout_url(protocol):
    """The URL that ends the login session for the given protocol."""
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
