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

from oslo_config import cfg
from oslo_log import log as logging

from manuka import config

import orcid

LOG = logging.getLogger(__name__)
CONF = cfg.CONF


def _get_orcid(result):
    return result['orcid-identifier']['path']


class Client(object):

    def __init__(self):
        self.api = orcid.PublicAPI(CONF.orcid.key, CONF.orcid.secret,
                                   CONF.orcid.sandbox)
        self.token = self.api.get_search_token_from_orcid()

    def search_by_text(self, text):
        results = self.api.search_generator('text:%s' % text,
                                            pagination=100,
                                            access_token=self.token)
        # Sometimes the result JSON include a 'null' ...
        return [_get_orcid(r) for r in results if r]

    def search_by_names(self, surname, first_name):
        query = 'family-name:%s+AND+given-names:%s' % (surname, first_name)
        results = self.api.search_generator(query,
                                            pagination=100,
                                            access_token=self.token)
        # Sometimes the result JSON include a 'null' ...
        return [_get_orcid(r) for r in results if r]

    def search_by_email(self, email):
        results = self.api.search('email:%s' % email,
                                  rows=2,
                                  access_token=self.token)
        if results['num-found'] == 0:
            return None
        elif results['num-found'] == 1:
            return _get_orcid(results['result'][0])
        else:
            raise Exception("email to ORCID mapping not unique")


def test(config_file="/home/ubuntu/manuka.conf"):
    config.init(args=[], conf_file=config_file)
    client = Client()

    print("by text -> ", client.search_by_text("Crawley"))
    print("by names -> ", client.search_by_names("Crawley", "Stephen"))
    print("by names -> ", client.search_by_names("Smith", "James"))
    print("by text (unknown) -> ",
          client.search_by_text("Cheeseburgher"))
    print("by email -> ",
          client.search_by_email("s.crawley@mailinator.com"))
    print("by email (unknown) -> ",
          client.search_by_email("foobar@mailinator.com"))
