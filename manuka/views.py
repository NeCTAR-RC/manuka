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
from urllib import parse

import flask
from flask import request
from flask import session
from oslo_config import cfg
from oslo_context import context
from oslo_log import log as logging

from manuka.extensions import db
from manuka import models
from manuka.worker import api as worker_api


default_bp = flask.Blueprint('default', __name__)
login_bp = flask.Blueprint('login', __name__, url_prefix='/login')

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class ShibbolethAttrMap(object):
    data = {'persistent-id': 'id',
            'cn': 'cn',
            'displayName': 'fullname',
            'givenName': 'firstname',
            'sn': 'surname',
            'uid': 'uid',
            'mail': 'mail',
            'eppn': 'eppn',
            'l': 'location',
            'description': 'description',
            'o': 'organisation',
            'affiliation': 'affiliation',
            'unscoped-affiliation': 'unscoped-affiliation',
            'assurance': 'assurance',
            'Shib-Identity-Provider': 'idp',
            'shared-token': 'shared_token',
            'homeOrganization': 'homeorganization',
            'homeOrganizationType': 'homeorganizationtype',
            'telephoneNumber': 'telephonenumber',
            'mobileNumber': 'mobilenumber',
            'eduPersonOrcid': 'orcid'}

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


@login_bp.route('/account_status')
def account_status():
    db_user = db.session.query(models.User).filter_by(
        persistent_id=session.get("user_id")).first()
    data = {"state": db_user.state}
    return json.dumps(data)


@login_bp.route('/', methods=('GET', 'POST'))
def root():
    shib_attrs = ShibbolethAttrMap.parse(request.environ)
    LOG.info("The AAF responded with: %s.", shib_attrs)
    errors = {}
    for field in ['id', 'mail', "fullname"]:
        if field not in shib_attrs:
            errors[field] = ("Required field '%s' can't be found." %
                             ShibbolethAttrMap.get_attr(field))

    if errors:
        LOG.error("The AAF IdP is not returning the required "
                  "attributes. The following are missing: %s. "
                  "The following are present: %s.",
                  ", ".join(errors.keys()), shib_attrs)
        error_values = list(errors.values())
        error_values.sort()
        data = {
            "title": "Error",
            "message": "Not enough details have been received from your "
                       "institution to allow you to log on to the cloud. "
                       "We need your id, your e-mail and your full name."
                       "<br />Please contact your institution and tell them "
                       "that their \"AAF IdP\" is broken!"
                       "<br />Copy and paste the details below into your "
                       "email to your institution's support desk."
                       "<br /><b>The following required fields are missing "
                       "from the AAF service:</b>",
            "errors": error_values}
        return flask.render_template("error.html", **data)

    external_id = db.session.query(models.ExternalId).filter_by(
        persistent_id=shib_attrs["id"]).first()
    db_user = external_id.user
    if not db_user:
        db_user = models.create_db_user(shib_attrs)

    session["user_id"] = shib_attrs["id"]

    current_terms_version = CONF.terms_version

    if request.form.get("agree") and db_user.state == "new":
        date_now = datetime.datetime.now()
        db_user.registered_at = date_now
        db_user.terms_accepted_at = date_now
        db_user.state = "registered"
        db_user.terms_version = current_terms_version
        models.update_db_user(db_user, external_id, shib_attrs)
        db.session.commit()
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

    if request.form.get("ignore_username"):
        # Ignore different username
        db_user.ignore_username_not_email = True
        db.session.commit()

    if db_user.terms_version != current_terms_version:
        data = {"title": "Terms and Conditions.",
                "terms_version": current_terms_version,
                "updated_terms": db_user.terms_version}
        return flask.render_template("terms_form.html", **data)

    if db_user.state == "registered":
        data = {"title": "Creating Account...",
                "support_url": CONF.support_url}
        return flask.render_template("creating_account.html", **data)

    if db_user.state == "created":
        set_username_as_email = False

        if request.form.get("change_username"):
            # User wants to change their username to match email
            set_username_as_email = True

        try:
            token, project_id, user = models.keystone_authenticate(
                db_user, set_username_as_email=set_username_as_email)
        except Exception as e:
            # TODO(russell) the error handing this exception is
            # to broad.

            # Martin: the error is occurring because Keystone has no
            # knowledge of the user, but we (fakeshib) do...  Which
            # raises an interesting philosophical question - how did
            # we get into this state?  BTW, if the user is in this
            # state, he has lost everything in the cloud, and is
            # likely to be unhappy...
            LOG.exception("A user known to manuka isn't known by "
                          "Keystone! Their user id is: %s", db_user.user_id)
            data = {
                "title": "Error",
                "message": 'Your details could not be found on the '
                           'central authentication server. '
                           'Thus you will <b><i>not</i></b> be able to '
                           'access the cloud! <br />Please contact <a '
                           'href="' + CONF.support_url + '">support</a> '
                           'to resolve this issue.'
                           '<br />The error message is:',
                "errors": [str(e)]}

            # We should perhaps redirect the user to a nicer more
            # useful error page...
            return flask.render_template("error.html", **data)

    models.update_db_user(db_user, external_id, shib_attrs)

    if user.name != user.email and not db_user.ignore_username_not_email:
        data = {"user": user}
        return flask.render_template("username_form.html", **data)

    # sjjf: default to the configured target URL, but allow the source
    # to specify a different return-path. The specified return path is
    # then verfied against a white list.
    target = CONF.default_target
    if request.args.get('return-path'):
        t = request.args.get('return-path')
        url_pieces = parse.urlparse(t)
        url_match = "{}://{}{}".format(url_pieces.scheme, url_pieces.netloc,
                                       url_pieces.path)
        if url_match in CONF.whitelist:
            target = t
        else:
            LOG.exception("Attempt to authenticate to a blocked URL: %s", t)
            data = {
                "title": "Authentication Error",
                "message": "You attempted to authenticate to the "
                + t
                + " URL, which is not permitted by this service."
                }
            return flask.render_template("error.html", **data)

    data = {"token": token,
            "tenant_id": project_id,
            "target": target}

    return flask.render_template("redirect.html", **data)


@default_bp.route('/terms.html')
def terms():
    template = "%s-terms_text.html" % CONF.terms_version
    return flask.render_template(template)
