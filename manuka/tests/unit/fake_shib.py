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


EMAIL = 'test@example.com'
DISPLAYNAME = "john smith"
ID = "1324"
IDP = 'https://test.idp'


class TestShibWrapper(object):

    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        environ['mail'] = EMAIL
        environ['displayName'] = DISPLAYNAME
        environ['persistent-id'] = ID
        environ['Shib-Identity-Provider'] = IDP
        return self.app(environ, start_response)
