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

from manuka import app
from manuka import extensions
from manuka.tests.unit import base


CONF = cfg.CONF

TEST_CONFIG = {
    "SECRET_KEY": "secret",
    "TESTING": True,
    "SQLALCHEMY_DATABASE_URI": "sqlite://",
    "SQLALCHEMY_TRACK_MODIFICATIONS": False,
}


class TestApp(base.TestCase):
    def _create_second_app(self, test_config):
        # The REST resources are registered on a module level singleton
        # which can only be initialised once per app.
        extensions.api.resources = []
        return app.create_app(test_config, init_config=False)

    def test_session_cookie_settings(self):
        self.assertEqual("Lax", self.app.config["SESSION_COOKIE_SAMESITE"])
        self.assertTrue(self.app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertTrue(self.app.config["SESSION_COOKIE_SECURE"])

    def test_session_cookie_insecure_for_development(self):
        CONF.set_override("session_cookie_secure", False, "flask")
        dev_app = self._create_second_app(TEST_CONFIG)
        self.assertFalse(dev_app.config["SESSION_COOKIE_SECURE"])
        self.assertEqual("Lax", dev_app.config["SESSION_COOKIE_SAMESITE"])

    def test_test_config_overrides_cookie_settings(self):
        test_config = dict(TEST_CONFIG, SESSION_COOKIE_SAMESITE="Strict")
        strict_app = self._create_second_app(test_config)
        self.assertEqual(
            "Strict", strict_app.config["SESSION_COOKIE_SAMESITE"]
        )
