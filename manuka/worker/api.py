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

import oslo_messaging

from manuka.common import rpc


class WorkerAPI(object):

    def __init__(self):
        target = oslo_messaging.Target(topic='manuka-worker', version='1.0')
        self._client = oslo_messaging.RPCClient(rpc.TRANSPORT, target)

    def create_user(self, ctxt, attrs):
        cctxt = self._client.prepare(version='1.0')
        cctxt.cast(ctxt, 'create_user', attrs=attrs)

    def refresh_orcid(self, ctxt, user_id):
        cctxt = self._client.prepare(version='1.0')
        cctxt.cast(ctxt, 'refresh_orcid', user_id=user_id)
