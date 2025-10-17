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


class ShibbolethAttrMap:
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

    @classmethod
    def parse(cls, environ):
        metadata = {}
        for k, v in cls.data.items():
            if environ.get(k):
                if k == "mail":
                    metadata[v] = environ.get(k).lower()
                else:
                    metadata[v] = environ.get(k)
        return metadata

    @classmethod
    def get_attr(cls, name):
        for k, v in cls.data.items():
            if name == v:
                return k


@login_bp.route("/account_status")
def account_status():
    external_id = (
        db.session.query(models.ExternalId)
        .filter_by(persistent_id=session.get("shib_user_id"))
        .first_or_404()
    )

    data = {"state": external_id.user.state}
    return json.dumps(data)


@login_bp.route("/", methods=("GET", "POST"))
def root():
    shib_attrs = ShibbolethAttrMap.parse(request.environ)
    LOG.info("The AAF responded with: %s.", shib_attrs)
    errors = {}
    for field in ["id", "mail", "fullname"]:
        if field not in shib_attrs:
            errors[field] = (
                f"Required field '{ShibbolethAttrMap.get_attr(field)}' "
                "can't be found."
            )

    if errors:
        LOG.error(
            "The AAF IdP is not returning the required "
            "attributes. The following are missing: %s. "
            "The following are present: %s.",
            ", ".join(errors.keys()),
            shib_attrs,
        )

    mail_value = shib_attrs.get("mail")
    if mail_value and not EMAIL_RE.match(mail_value):
        LOG.error(
            "The AAF IdP is returning a bad 'mail' attribute: '%s'", mail_value
        )
        errors["mail"] = (
            "The '{}' field must be one RFC 5322 <addr-spec>: "
            "the value provided is '{}'".format(
                ShibbolethAttrMap.get_attr("mail"), mail_value
            )
        )

    if errors:
        error_values = list(errors.values())
        error_values.sort()
        data = {
            "title": "Error",
            "message": "Not enough details have been received from your "
            "institution to allow you to log on to the cloud. "
            "We need your id, your e-mail and your full name."
            "<br />Please contact your institution and tell them "
            'that their "AAF IdP" is broken!'
            "<br />Copy and paste the details below into your "
            "email to your institution's support desk."
            "<br /><b>The following required fields are missing "
            "or incorrect from the AAF service:</b>",
            "errors": error_values,
        }
        return flask.render_template("error.html", **data)

    external_id = (
        db.session.query(models.ExternalId)
        .filter_by(persistent_id=shib_attrs["id"])
        .first()
    )
    if not external_id:
        db_user, external_id = models.create_db_user(shib_attrs)
    else:
        db_user = external_id.user

    session["shib_user_id"] = shib_attrs["id"]

    current_terms_version = CONF.terms_version

    if request.form.get("agree") and db_user.state == "new":
        date_now = datetime.datetime.now()
        db_user.registered_at = date_now
        db_user.terms_accepted_at = date_now
        db_user.state = "registered"
        db_user.terms_version = current_terms_version
        models.update_db_user(db_user, external_id, shib_attrs)
        db.session.commit()
        LOG.info("User %s accepted terms", db_user)
        # after registering present the user with a page indicating
        # there account is being created
        worker = worker_api.WorkerAPI()
        ctxt = context.RequestContext()
        worker.create_user(ctxt, shib_attrs)

    if request.form.get("agree") and db_user.state == "created":
        # New terms version accepted
        db_user.terms_version = current_terms_version
        db_user.terms_accepted_at = datetime.datetime.now()
        models.update_db_user(db_user, external_id, shib_attrs)
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
                "message": "Your details could not be found on the "
                "central authentication server. "
                "Thus you will <b><i>not</i></b> be able to "
                "access the cloud! <br />Please contact <a "
                'href="' + CONF.support_url + '">support</a> '
                "to resolve this issue."
                "<br />The error message is:",
                "errors": [str(e)],
            }

            # We should perhaps redirect the user to a nicer more
            # useful error page...
            return flask.render_template("error.html", **data)

    models.update_db_user(db_user, external_id, shib_attrs)

    if user.name != user.email and not db_user.ignore_username_not_email:
        LOG.info("User %s username and email do not match", db_user)
        data = {"user": user}
        return flask.render_template("username_form.html", **data)

    # sjjf: default to the configured target URL, but allow the source
    # to specify a different return-path. The specified return path is
    # then verified against a white list.
    target = CONF.default_target
    if request.args.get("return-path"):
        t = request.args.get("return-path")
        url_pieces = parse.urlparse(t)
        url_match = (
            f"{url_pieces.scheme}://{url_pieces.netloc}{url_pieces.path}"
        )
        if url_match in CONF.whitelist:
            target = t
        else:
            LOG.exception("Attempt to authenticate to a blocked URL: %s", t)
            data = {
                "title": "Authentication Error",
                "message": "You attempted to authenticate to the "
                + t
                + " URL, which is not permitted by this service.",
            }
            return flask.render_template("error.html", **data)

    data = {"token": token, "tenant_id": project_id, "target": target}

    return flask.render_template("redirect.html", **data)


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
    external_id = (
        db.session.query(models.ExternalId)
        .filter_by(persistent_id=session.get("shib_user_id"))
        .first_or_404()
    )
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
    external_id = (
        db.session.query(models.ExternalId)
        .filter_by(persistent_id=session.get("shib_user_id"))
        .first_or_404()
    )
    user = external_id.user
    user.orcid = None
    user.orcid_token = None
    db.session.add(user)
    db.session.commit()

    return flask.redirect(redirect_url)
