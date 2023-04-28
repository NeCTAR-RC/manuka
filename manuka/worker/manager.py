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

import functools

from freshdesk.v2 import api as fd_api
import keystoneauth1
from oslo_config import cfg
from oslo_log import log as logging

from manuka import app
from manuka.common import clients
from manuka.common import keystone
from manuka.extensions import db
from manuka import models
from manuka.worker import notifier
from manuka.worker import utils


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def app_context(f):
    @functools.wraps(f)
    def decorated(self, *args, **kwargs):
        with self.app.app_context():
            return f(self, *args, **kwargs)
    return decorated


class Manager(object):

    def __init__(self):
        self.app = app.create_app(init_config=False)

    @app_context
    def create_user(self, attrs):
        k_session = keystone.KeystoneSession()
        session = k_session.get_session()
        client = clients.get_admin_keystoneclient(session)

        # get the user from the database, if this fails then they
        # shouldn't be created
        external_id = db.session.query(models.ExternalId).filter_by(
            persistent_id=attrs["id"]).first()
        db_user = external_id.user

        idp = attrs.get('idp')
        domain = utils.get_domain_for_idp(idp)
        LOG.info("Using project domain_id=%s", domain)
        project = utils.create_project(client, "pt-%s" % db_user.id,
                                       "%s's project trial." %
                                       attrs["fullname"],
                                       domain)
        LOG.info('Created Project %s', project.name)

        try:
            user = utils.create_user(client, attrs["mail"],
                                     attrs["mail"], project,
                                     attrs['fullname'])
        except keystoneauth1.exceptions.http.Conflict as e:
            notifier.send_message(session=session,
                                  email=attrs.get('mail'),
                                  context={'user': attrs},
                                  template='duplicate_account.tmpl',
                                  subject='Nectar Cloud login issue')
            client.projects.delete(project.id)
            LOG.info(f"Deleted project {project.name}")
            db_user.state = "duplicate"
            db.session.add(db_user)
            db.session.commit()

            raise e
        else:
            LOG.info('Created user %s', user.name)

        # Attempt to create a contact in Freshdesk with their proper IdP
        # provided name and email
        try:
            fd = fd_api.API(CONF.freshdesk.domain, CONF.freshdesk.key)
            contact = fd.contacts.create_contact(
                name=attrs["fullname"],
                email=attrs["mail"])
            LOG.info('Created Freshdesk contact: %s', contact)
        except Exception as e:
            # FD contact creation should not be treated as fatal, just log it
            LOG.warning("Ignoring Freshdesk contact creation error: %s", e)

        utils.add_user_roles(client, project=project, user=user,
                             roles=['Member'])

        db_user.keystone_user_id = user.id
        db_user.state = "created"
        db.session.add(db_user)
        db.session.commit()

        utils.send_welcome_email(user, project)
        LOG.info('Send welcome email to %s', user.email)

        token, project_id, updated_user = models.keystone_authenticate(
            db_user, project_id=project.id)

        utils.add_security_groups(user.id, project.id, token)
        LOG.info("%s: Added security groups.", user.id)
        utils.set_nova_quota(session, project.id)
        LOG.info("%s: Set nova quota", user.id)
        swift_quota = CONF.swift.default_quota_gb
        if swift_quota is not None:
            utils.set_swift_quota(session, project.id, swift_quota)
            LOG.info("%s: Set swift quota to %sGB.", user.id, swift_quota)
        LOG.info('%s: Completed Processing.', user.id)

    @app_context
    def refresh_orcid(self, user_id):
        db_user = db.session.query(models.User).get(user_id)
        utils.refresh_orcid(db_user)
