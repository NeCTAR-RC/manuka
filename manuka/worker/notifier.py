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

import jinja2
from oslo_config import cfg
from oslo_log import log as logging
from stevedore import driver as stevedore_driver
from taynacclient import client as taynac_client


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def send_message(session, email, context, template, subject):
    notifier = stevedore_driver.DriverManager(
                namespace='manuka.notifier',
                name=CONF.notifier,
                invoke_on_load=True
            ).driver

    return notifier.send_message(session, email, context, template, subject)


class BaseNotifier(object):

    @staticmethod
    def render_template(tmpl, context={}):
        template_dir = os.path.realpath(os.path.join(os.path.dirname(__file__),
                                                     '../',
                                                     'templates'))
        LOG.debug(f"Using template_dir {template_dir}")
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
        template = env.get_template(tmpl)
        template = template.render(context)
        return template


class TaynacNotifier(BaseNotifier):

    def send_message(self, session, email, context, template, subject):
        client = taynac_client.Client('1', session=session)
        body = self.render_template(template, context)
        message = client.messages.send(recipient=email, subject=subject,
                                       body=body)
        LOG.info(f"Created message {message}, requester={email}")
        return message


class LoggingNotifier(BaseNotifier):

    def send_message(self, session, email, context, template, subject):
        body = self.render_template(template, context)
        LOG.info("Would send email to %s", email)
        LOG.info("Subject: %s", subject)
        LOG.info("%s", body)
