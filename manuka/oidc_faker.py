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

"""A stand-in OpenID Connect provider for local development.

Enabled with [oidc] fake = true. Instead of sending the browser to the
provider, /oidc/login/ lands on a form at /oidc/fake/ where the
developer types the claims; the form then returns to the callback with
those claims encoded in the authorisation code. Together with
fake_shib this lets every login and linking flow run in one browser
without Keycloak or an identity federation.
"""

import base64
import json

import flask
from flask import request


FAKE_ISSUER = "https://fake-oidc.invalid/realms/nectar"

FORM = """
<html>
<body>
<h1>FAKE OIDC PROVIDER</h1>
<p>Fill in the claims to return. The shared token, subject-id and eppn are
what link this login to a Shibboleth identity; paste the values from a
fake Shibboleth session to exercise automatic linking.</p>
<form method="post" action="">
<input type="hidden" name="redirect_uri" value="{redirect_uri}"/>
<table>
<tr><td>Subject (sub)</td><td><input name="sub" value="{sub}"/></td></tr>
<tr><td>Email</td><td><input name="email" value="{email}"/></td></tr>
<tr><td>Name</td><td><input name="name" value="{name}"/></td></tr>
<tr><td>Given name</td><td><input name="given_name" value="{given_name}"/></td></tr>
<tr><td>Family name</td><td><input name="family_name" value="{family_name}"/></td></tr>
<tr><td>eppn</td><td><input name="eduperson_principal_name" value=""/></td></tr>
<tr><td>Shared token</td><td><input name="au_edu_person_shared_token" value=""/></td></tr>
<tr><td>subject-id</td><td><input name="subject_id" value=""/></td></tr>
<tr><td>pairwise-id</td><td><input name="pairwise_id" value=""/></td></tr>
<tr><td>Affiliation</td><td><input name="eduperson_affiliation" value="member"/></td></tr>
<tr><td>Home organisation</td><td><input name="schac_home_organization" value="example.edu"/></td></tr>
<tr><td>Federation (broker alias)</td><td><input name="identity_provider" value="aaf"/></td></tr>
</table>
<input type="submit" name="fakeoidc" value="Log in"/>
</form>
</body>
</html>
"""

CLAIM_FIELDS = (
    "sub",
    "email",
    "name",
    "given_name",
    "family_name",
    "eduperson_principal_name",
    "au_edu_person_shared_token",
    "subject_id",
    "pairwise_id",
    "eduperson_affiliation",
    "schac_home_organization",
    "identity_provider",
)


def encode_code(claims):
    return base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()


def decode_code(code):
    return json.loads(base64.urlsafe_b64decode(code.encode()).decode())


class FakeOIDCClient:
    """Mimics the Authlib client against the form at /oidc/fake/."""

    def authorize_redirect(self, redirect_uri=None, **kwargs):
        return flask.redirect(
            flask.url_for("oidc.oidc_fake", redirect_uri=redirect_uri)
        )

    def authorize_access_token(self):
        claims = decode_code(request.args.get("code", ""))
        claims.setdefault("iss", FAKE_ISSUER)
        return {"access_token": "fake", "userinfo": claims}

    def userinfo(self, token=None):
        return dict(token["userinfo"])

    def load_server_metadata(self):
        return {"issuer": FAKE_ISSUER}


def fake_form():
    """Show the claim form, or return to the callback with the claims."""
    if request.method == "POST" and request.form.get("fakeoidc"):
        claims = {
            field: request.form.get(field, "").strip()
            for field in CLAIM_FIELDS
            if request.form.get(field, "").strip()
        }
        claims["iss"] = FAKE_ISSUER
        redirect_uri = request.form.get("redirect_uri") or flask.url_for(
            "oidc.oidc_callback"
        )
        return flask.redirect(
            f"{redirect_uri}?code={encode_code(claims)}&state=fake"
        )
    return FORM.format(
        redirect_uri=request.args.get("redirect_uri", ""),
        sub="fake-sub-1",
        email="fake.user@example.edu",
        name="Fake User",
        given_name="Fake",
        family_name="User",
    )
