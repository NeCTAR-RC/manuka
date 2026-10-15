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

"""OpenID Connect client support.

Manuka is a confidential OpenID Connect client of Keycloak. This module
owns the Authlib client registration and the retrieval of identity
claims; the login views live in manuka.views and reach the client
through get_client(), which is the single point tests replace.
"""

from authlib.common.errors import AuthlibBaseError
from authlib.integrations.flask_client import OAuth
import flask
from oslo_config import cfg
from oslo_log import log as logging


CONF = cfg.CONF
LOG = logging.getLogger(__name__)

CLIENT_NAME = "keycloak"
EXTENSION_KEY = "manuka.oidc"
METADATA_PATH = "/.well-known/openid-configuration"


# Everything Authlib raises while exchanging the code and validating
# the ID token (mismatching state, token errors, bad signatures).
ProviderError = AuthlibBaseError


class OIDCError(Exception):
    """The provider returned identity information manuka cannot use."""


def server_metadata_url():
    """The discovery document URL, derived from the issuer by default."""
    if CONF.oidc.server_metadata_url:
        return CONF.oidc.server_metadata_url
    return CONF.oidc.issuer.rstrip("/") + METADATA_PATH


def init_app(app):
    """Attach an OpenID Connect client to the app when login is enabled.

    The provider metadata is only fetched on first use, so a process
    that never logs anyone in (the worker) never contacts the provider.
    """
    oauth = OAuth(app)
    app.extensions[EXTENSION_KEY] = oauth
    if not CONF.oidc.enabled:
        LOG.debug("OpenID Connect login is disabled")
        return None
    return oauth.register(
        CLIENT_NAME,
        client_id=CONF.oidc.client_id,
        client_secret=CONF.oidc.client_secret,
        server_metadata_url=server_metadata_url(),
        client_kwargs={
            "scope": " ".join(CONF.oidc.scopes),
            "code_challenge_method": "S256",
        },
    )


def get_client():
    """The registered client, or None when login is disabled."""
    oauth = flask.current_app.extensions.get(EXTENSION_KEY)
    if oauth is None:
        return None
    return oauth.create_client(CLIENT_NAME)


def fetch_claims(client, token):
    """Return the identity claims for a freshly obtained token.

    The claims of the validated ID token are the base. When
    use_userinfo_endpoint is set the userinfo response is merged over
    them, after checking that it describes the same subject.
    """
    claims = dict(token.get("userinfo") or {})
    if CONF.oidc.use_userinfo_endpoint:
        userinfo = dict(client.userinfo(token=token))
        if claims.get("sub") and userinfo.get("sub") != claims.get("sub"):
            raise OIDCError("userinfo subject does not match the ID token")
        claims.update(userinfo)
    for required in ("iss", "sub"):
        if not claims.get(required):
            raise OIDCError(f"'{required}' claim missing from the ID token")
    return claims
