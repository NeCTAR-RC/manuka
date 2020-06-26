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

import io
import random
import string
from urllib.parse import parse_qs
from urllib.parse import urljoin

from oslo_config import cfg
from werkzeug.wrappers import Request

from manuka import models

CONF = cfg.CONF

FAKESHIB_FORM = """
<html>
<body>
<h1>FAKESHIB!!!!!!!!!!!!!!!</h1>
<form method="post" action="">
Username: <input type="text" name="username"/>
<input type="submit" name="fakeshib" value="Shibboleth"/>
</form>
</body>
</html>
"""

shib_headers = ['cn', 'displayName', 'givenName', 'sn', 'uid', 'eppn',
                'l', 'employeetype', 'description', 'o', 'affiliation',
                'unscoped-affiliation', 'assurance', 'Shib-Identity-Provider',
                'shared-token', 'homeOrganization', 'homeOrganizationType',
                'telephoneNumber', 'mobileNumber', 'eduPersonOrcid']


def fake_shibboleth_filter_factory(global_conf):
    def filter(app):
        return FakeShibboleth(app)
    return filter


class FakeShibboleth(object):
    def __init__(self, app):
        self.app = app

    def _query_parameters(self, qs):
        """Extract the query parameters.
        """
        if isinstance(qs, bytes):
            qs = qs.decode('utf8')
        return parse_qs(qs)

    def __call__(self, environ, start_response):
        session = environ["beaker.session"]
        params = {}
        request = Request(environ)
        if not request.path.startswith('/login'):
            return self.app(environ, start_response)

        # Handle logout
        if environ['PATH_INFO'] == '/Shibboleth.sso/Logout':
            params = self._query_parameters(environ.get('QUERY_STRING', ""))
            referer = environ.get('HTTP_REFERER', "")
            if params.get("return"):
                ret = params["return"][0]
            else:
                ret = ""
            url = urljoin(referer, ret)
            session.delete()
            start_response('303 OK', [('Content-type', 'text/html'),
                                      ('Content-Length', "0"),
                                      ('Location', url)])
            return []

        # Handle Login
        if environ['REQUEST_METHOD'] == 'POST' and not session.get("fakeshib"):
            body = request.get_data()
            environ['wsgi.input'] = io.BytesIO(body)
            params = self._query_parameters(body)
        output = []
        if (environ['REQUEST_METHOD'] == 'POST'
            and params.get("fakeshib") == ["Shibboleth"]):
            username = params["username"][0]
            session["fakeshib"] = {}
            session["fakeshib"]["persistent-id"] = username
            session["fakeshib"]["mail"] = username

            # seed the PRNG with the user name so that the random
            # attributes don't change each time the user logs in
            random.seed(username)

            # encode shib headers
            for header in shib_headers:
                if header == 'affiliation':
                    value = random.choice(models.AFFILIATION_VALUES)
                elif header == 'eduPersonOrcid':
                    if CONF.fake_shib_no_shib_orcid:
                        value = None
                    else:
                        # realistic looking orcid
                        value = '0000-0000-0001-%s' \
                                (''.join(random.choice(string.digits)
                                         for i in range(4)))
                else:
                    # include header name in value to make bugs more obvious
                    value = "%s-%s" % \
                            (header,
                             ''.join(random.choice(string.ascii_letters
                                                   + string.digits)
                                     for i in range(20)))
                if value:
                    session["fakeshib"][header] = value
            session.save()

        # Handle already logged in
        if session.get("fakeshib"):
            environ.update(session["fakeshib"])
            return self.app(environ, start_response)

        # Handle not logged in
        output.append(FAKESHIB_FORM)
        utf8 = [line.encode('utf8') for line in output]
        utf8_len = sum(len(line) for line in utf8)
        start_response('200 OK', [('Content-type', 'text/html; charset=utf-8'),
                                  ('Content-Length', str(utf8_len))])
        return utf8
