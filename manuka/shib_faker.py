import io
import random
import string
from werkzeug.wrappers import Request
from urllib.parse import parse_qs
from urllib.parse import urljoin

from manuka import models

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
        if (environ['REQUEST_METHOD'] == 'POST' and params.get("fakeshib") == ["Shibboleth"]):
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
                else:
                    value = ''.join(random.choice(string.ascii_letters
                                                  + string.digits)
                                    for i in range(20))
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
