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

import pdb

from oslo_config import cfg
from oslo_log import log as logging

from manuka import config

import orcid

LOG = logging.getLogger(__name__)    
CONF = cfg.CONF


class Client(object):

    def __init__(self):
        self.api = orcid.PublicAPI(CONF.orcid.key, CONF.orcid.secret,
                              CONF.orcid.sandbox)
        self.token = self.api.get_search_token_from_orcid()

    def search_by_text(self, text):
        results = self.api.search('text:%s' % text,
                                  access_token=self.token)
        return [r['orcid-identifier']['path'] for r in results['result']]

    def search_by_email(self, email):
        results = self.api.search('email:%s' % email,
                                  access_token=self.token)
        if results['num-found'] == 0:
            return None
        elif results['num-found'] == 1:
            return results['result'][0]['orcid-identifier']['path']
        else:
            raise Exception("email to ORCID mapping not unique")


def test(config_file):
    key = 'APP-L70R3Q2JPGE4M31O' 
    secret = 'ce98cf88-0159-4e15-a6f4-5e2e09693e81'

    api = orcid.PublicAPI(key, secret, sandbox=True)
    search_token = api.get_search_token_from_orcid()
    results = api.search('text:Crawley', access_token=search_token)
    orcids = [r['orcid-identifier']['path'] for r in results['result']]
    print(orcids)

    results = api.search('email:s.crawley@mailinator.com',
                         access_token=search_token)
    orcids = [r['orcid-identifier']['path'] for r in results['result']]
    print(orcids)

    config.init(args=[], conf_file=config_file)
    CONF.set_override('key', key, 'orcid')
    CONF.set_override('secret', secret, 'orcid')
    CONF.set_override('sandbox', True, 'orcid')
    client = Client()

    print(client.search_by_text("Crawley"))
    print(client.search_by_text("Cheeseburgher"))
    print(client.search_by_email("s.crawley@mailinator.com"))
    print(client.search_by_email("foobar@mailinator.com"))
