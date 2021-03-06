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

import time

import orcid
from oslo_config import cfg
from oslo_log import log as logging
from requests import exceptions


LOG = logging.getLogger(__name__)
CONF = cfg.CONF


class Client(object):

    def __init__(self, max_retries=None, retry_delay=None):
        self.max_retries = max_retries or CONF.orcid.max_retries
        self.retry_delay = retry_delay or CONF.orcid.retry_delay
        proxies = {}
        if CONF.orcid.http_proxy:
            proxies['http'] = CONF.orcid.http_proxy
        if CONF.orcid.https_proxy:
            proxies['https'] = CONF.orcid.https_proxy
        self.api = orcid.PublicAPI(CONF.orcid.key, CONF.orcid.secret,
                                   CONF.orcid.sandbox,
                                   timeout=CONF.orcid.timeout,
                                   proxies=proxies)
        self.token = self.api.get_search_token_from_orcid()

    @staticmethod
    def _get_orcid(result):
        return result['orcid-identifier']['path']

    def search_by_text(self, text):
        return self._search('text:%s' % text)

    def search_by_names(self, surname, first_name):
        query = 'family-name:%s+AND+given-names:%s' % (surname, first_name)
        return self._search(query)

    def _handle_http_error(self, ex):
        if ex.response and ex.response.status_code in [500, 503]:
            if self.tries < self.max_retries:
                LOG.info("Sleeping and retrying request: url %s",
                         ex.request.url)
                self.tries += 1
                time.sleep(self.retry_delay)
                return
        raise ex

    def _search(self, query):
        self.tries = 0
        while True:
            try:
                results = self.api.search_generator(query,
                                                    pagination=100,
                                                    access_token=self.token)
                # Sometimes the result JSON includes a 'null' ...
                return [self._get_orcid(r) for r in results if r]
            except exceptions.HTTPError as ex:
                self._handle_http_error(ex)

    def search_by_email(self, email):
        self.tries = 0
        while True:
            try:
                results = self.api.search('email:%s' % email,
                                          rows=2,
                                          access_token=self.token)
                if results['num-found'] == 0:
                    return None
                elif results['num-found'] == 1:
                    return self._get_orcid(results['result'][0])
                else:
                    # This indicates something is fundamentally wrong
                    # in the service.  This relation is one to one (or
                    # one to none).
                    raise Exception("email to ORCID mapping not unique")
            except exceptions.HTTPError as ex:
                self._handle_http_error(ex)
