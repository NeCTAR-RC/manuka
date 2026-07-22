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

import os
import sys

from oslo_config import cfg
from oslo_log import log as logging
import sentry_sdk

from manuka import version


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def setup():
    """Enable error reporting to GlitchTip/Sentry.

    A no-op unless a DSN is set in the [sentry] section of the config
    file (or the SENTRY_DSN environment variable). Once enabled, the
    sentry-sdk default integrations report unhandled exceptions and
    ERROR level log messages.
    """
    dsn = CONF.sentry.dsn or os.environ.get("SENTRY_DSN")
    if not dsn:
        return False
    sentry_sdk.init(
        dsn=dsn,
        environment=CONF.sentry.environment,
        release=f"manuka@{version.version_info.release_string()}",
        # GlitchTip does not support sessions
        auto_session_tracking=False,
    )
    sentry_sdk.set_tag("command", os.path.basename(sys.argv[0]))
    LOG.debug("Sentry error reporting enabled")
    return True
