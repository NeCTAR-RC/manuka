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

"""A stand-in for the Authlib OpenID Connect client used in tests."""

from authlib.integrations.base_client import OAuthError
import flask


ISSUER = "https://keycloak.example/realms/nectar"
AUTHORIZE_URL = ISSUER + "/protocol/openid-connect/auth"
END_SESSION_URL = ISSUER + "/protocol/openid-connect/logout"

SUB = "0f6f7c1a-1d2e-4b3c-9a8b-7c6d5e4f3a2b"
EMAIL = "test@example.com"
DISPLAYNAME = "john smith"
EPPN = "jsmith@example.edu"
SHARED_TOKEN = "AbCdEf1234567890SharedToken"
SUBJECT_ID = "abc123def456@example.edu"
PAIRWISE_ID = "pw-abc123@example.edu"
HOME_ORG = "example.edu"
FEDERATION = "aaf"

CLAIMS = {
    "iss": ISSUER,
    "sub": SUB,
    "aud": "manuka",
    "email": EMAIL,
    "name": DISPLAYNAME,
    "given_name": "john",
    "family_name": "smith",
    "preferred_username": "jsmith",
    "eduperson_principal_name": EPPN,
    "au_edu_person_shared_token": SHARED_TOKEN,
    "subject_id": SUBJECT_ID,
    "pairwise_id": PAIRWISE_ID,
    "eduperson_affiliation": ["staff", "member"],
    "schac_home_organization": HOME_ORG,
    "identity_provider": FEDERATION,
}


class FakeOIDCClient:
    """Behaves like FlaskOAuth2App without talking to a provider.

    ``claims`` are returned as the ID token claims by
    authorize_access_token(). Set ``error`` to make the token exchange
    fail the way Authlib does, and ``userinfo`` to return different
    claims from the userinfo endpoint.
    """

    def __init__(self, claims=None, error=None, userinfo=None):
        self.claims = dict(CLAIMS if claims is None else claims)
        self.error = error
        self.userinfo_claims = userinfo
        self.redirect_calls = []
        self.userinfo_calls = 0

    def authorize_redirect(self, redirect_uri=None, **kwargs):
        self.redirect_calls.append((redirect_uri, kwargs))
        return flask.redirect(AUTHORIZE_URL + "?state=fake-state")

    def authorize_access_token(self):
        if self.error:
            raise OAuthError(error=self.error)
        return {
            "access_token": "fake-access-token",
            "id_token": "fake-id-token",
            "token_type": "Bearer",
            "userinfo": dict(self.claims),
        }

    def userinfo(self, token=None):
        self.userinfo_calls += 1
        return dict(
            self.claims
            if self.userinfo_claims is None
            else self.userinfo_claims
        )

    def load_server_metadata(self):
        return {
            "issuer": ISSUER,
            "authorization_endpoint": AUTHORIZE_URL,
            "end_session_endpoint": END_SESSION_URL,
        }
