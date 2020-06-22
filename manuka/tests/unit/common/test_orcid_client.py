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

from unittest.mock import patch

from requests import exceptions

from manuka.common import orcid_client
from manuka.tests.unit import base

SEARCH_RESULTS = {
    'text:Foo': ['0000-0001-0000-0001',
                 '0000-0001-0000-0002'],
    'email:foo@bar.com': ['0000-0001-0000-0001'],
    'family-name:Spriggs+AND+given-names:Jim': ['0000-0001-0000-0003'],
}


class FakePublicAPI(object):

    def __init__(self, *args, **kwargs):
        pass

    def get_search_token_from_orcid(self):
        return ""

    def search(self, query, **kwargs):
        orcids = SEARCH_RESULTS.get(query, [])
        result = [self._orcid_to_result(o) for o in orcids]
        return {'result': result,
                'num-found': len(orcids)}

    def search_generator(self, query, **kwargs):
        orcids = SEARCH_RESULTS.get(query, [])
        for o in orcids:
            yield self._orcid_to_result(o)

    def _orcid_to_result(self, orcid):
        return {
            'orcid-identifier':
            {
                'uri': 'https://sandbox.orcid.org/' + orcid,
                'path': orcid,
                'host': 'sandbox.orcid.org'
            }
        }


class FakeRequest(object):
    def __init__(self, url="https://testing", **kwargs):
        self.url = url


class FakeResponse(object):
    def __init__(self, status_code=500, **kwargs):
        self.status_code = status_code


class FakeHTTPError(exceptions.HTTPError):
    def __init__(self, **kwargs):
        super().__init__(request=FakeRequest(**kwargs),
                         response=FakeResponse(**kwargs))


class UnreliableFakePublicAPI(FakePublicAPI):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.last_query = None

    def search(self, query, **kwargs):
        self._do_fail(query)
        return super().search(query, **kwargs)

    def search_generator(self, query, **kwargs):
        self._do_fail(query)
        return super().search_generator(query, **kwargs)

    def _do_fail(self, query):
        # First request for a given query fail with a fake 500 response.
        if query != self.last_query:
            self.last_query = query
            raise FakeHTTPError()


class FailingFakePublicAPI(UnreliableFakePublicAPI):

    def _do_fail(self, query):
        # Always fail
        raise FakeHTTPError()


class OrcidClientTest(base.TestCase):

    @patch('orcid.PublicAPI', new=FakePublicAPI)
    def test_orcid_searches(self):
        client = orcid_client.Client()
        self.assertEqual('0000-0001-0000-0001',
                         client.search_by_email('foo@bar.com'))
        self.assertIsNone(client.search_by_email('baz@bar.com'))

        orcids = client.search_by_text("Foo")
        self.assertEqual(2, len(orcids))

        orcids = client.search_by_names("Spriggs", "Jim")
        self.assertEqual(1, len(orcids))

    @patch('orcid.PublicAPI', new=UnreliableFakePublicAPI)
    def test_orcid_searches_unreliable(self):
        client = orcid_client.Client(retry_delay=0)
        self.assertEqual('0000-0001-0000-0001',
                         client.search_by_email('foo@bar.com'))
        self.assertIsNone(client.search_by_email('baz@bar.com'))

        orcids = client.search_by_text("Foo")
        self.assertEqual(2, len(orcids))

        orcids = client.search_by_names("Spriggs", "Jim")
        self.assertEqual(1, len(orcids))

    @patch('orcid.PublicAPI', new=FailingFakePublicAPI)
    def test_orcid_searches_failing(self):
        client = orcid_client.Client(retry_delay=0)
        with self.assertRaises(exceptions.HTTPError):
            client.search_by_email('foo@bar.com')
        with self.assertRaises(exceptions.HTTPError):
            client.search_by_text("Foo")
        with self.assertRaises(exceptions.HTTPError):
            client.search_by_names("Spriggs", "Jim")
