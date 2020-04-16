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


import manuka
from manuka.common import clients
from manuka.common import keystone
from manuka.extensions import db
from manuka import models
from manuka.worker import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class Manager(object):

    def __init__(self):
        self.app = manuka.create_app()

    def create_user(self, shib_attrs):
        k_session = keystone.KeystoneSession()
        session = k_session.get_session()
        client = clients.get_admin_keystoneclient(session)

        # get the user from the database, if this fails then they
        # shouldn't be created
        with self.app.app_context():
            shib_user = db.session.query(models.User).filter_by(
                persistent_id=shib_attrs["id"]).first()

        idp = shib_attrs.get('idp')
        domain = utils.get_domain_for_idp(idp)
        LOG.info("Using project domain_id=%s", domain)
        project = utils.create_project(client, "pt-%s" % shib_user.id,
                                       "%s's project trial." %
                                       shib_attrs["fullname"],
                                       domain)
        LOG.info('Created Project %s', project.name)

        user = utils.create_user(client, shib_attrs["mail"],
                                 shib_attrs["mail"], project,
                                 shib_attrs['fullname'])
        LOG.info('Created user %s', user.name)

        utils.add_user_roles(client, project=project, user=user,
                             roles=['Member'])

        with self.app.app_context():
            shib_user.user_id = user.id
            shib_user.state = "created"
            db.session.add(shib_user)
            db.session.commit()

        utils.send_welcome_email(user, project)
        LOG.info('Send welcome email to %s', user.email)

        token, project_id, updated_user = models.keystone_authenticate(
            user.id, project_id=project.id)

        utils.add_security_groups(user.id, project.id, token)
        LOG.info("%s: Added security groups.", user.id)
        utils.set_nova_quota(session, project.id)
        LOG.info("%s: Set nova quota", user.id)
        swift_quota = CONF.swift.default_quota_gb
        if swift_quota is not None:
            utils.set_swift_quota(session, project.id, swift_quota)
            LOG.info("%s: Set swift quota to %sGB.", user.id, swift_quota)
        LOG.info('%s: Completed Processing.', user.id)
