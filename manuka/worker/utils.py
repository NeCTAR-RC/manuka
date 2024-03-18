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

import base64
import logging
import os
import time

import flask
from oslo_config import cfg
from requests import exceptions

from manuka.common import clients
from manuka.common import email_utils
from manuka.extensions import db
from manuka import models


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def create_user(client, name, email, project=None, full_name=None):
    """Add a new user"""
    password = str(base64.encodebytes(os.urandom(16))[:20], 'utf-8')
    user = client.users.create(name=name,
                               password=password,
                               email=email,
                               domain='default',
                               default_project=project)
    return client.users.update(user.id, full_name=full_name)


def create_project(client, name, description, domain='default'):
    """Add a new project"""
    return client.projects.create(name=name,
                                  domain=domain,
                                  description=description)


def add_user_roles(client, user, project, roles=[]):
    """Add a roles for a particular user and project.
    """
    # add default role to user.
    for role in get_roles(client, roles):
        LOG.info('Adding role %s to user %s project %s',
                 role.name, user.name, project.name)
        client.roles.grant(user=user, role=role, project=project)


def get_roles(client, role_names):
    roles = []
    role_list = client.roles.list()
    LOG.debug('Roles %s', role_list)

    for role in role_list:
        LOG.debug('Testing role %s in %s', role.name, role_names)
        if role.name in role_names:
            roles.append(role)
    return roles


def get_domain_for_idp(idp):
    mapping = db.session.query(models.DomainIdpMapping).filter_by(
        idp_entity_id=idp).first()

    if mapping:
        return mapping.domain_id
    return 'default'


def add_security_groups(user_id, project_id, token):
    """Add the security groups to the user's project.

    Security groups that are added are:
    HTTP - port 80/443
    ICMP - all
    SSH - port 22
    """
    c = clients.get_openstack_client(project_id, token)

    group = c.network.create_security_group(
        name="icmp", description="Allow ICMP (eg. ping)")
    c.network.create_security_group_rule(
        security_group_id=group.id, protocol="icmp",
        direction='ingress', remote_ip_prefix="0.0.0.0/0")
    LOG.info('%s: Added Security Group ICMP.', user_id)

    group = c.network.create_security_group(
        name="ssh", description="Allow SSH")
    c.network.create_security_group_rule(
        security_group_id=group.id, protocol="tcp",
        port_range_min=22, port_range_max=22,
        direction='ingress', remote_ip_prefix="0.0.0.0/0")
    LOG.info('%s: Added Security Group SSH.', user_id)

    group = c.network.create_security_group(
        name="http", description="Allow HTTP/S")
    c.network.create_security_group_rule(
        security_group_id=group.id, protocol="tcp",
        port_range_min=80, port_range_max=80,
        direction='ingress', remote_ip_prefix="0.0.0.0/0")
    c.network.create_security_group_rule(
        security_group_id=group.id, protocol="tcp",
        port_range_min=443, port_range_max=443,
        direction='ingress', remote_ip_prefix="0.0.0.0/0")
    LOG.info('%s: Added Security Group HTTP.', user_id)


def set_nova_quota(session, project_id):
    nclient = clients.get_admin_nova_client(session)
    nclient.quotas.update(tenant_id=project_id,
                          cores=2,
                          instances=2,
                          ram=8192)


def set_swift_quota(session, project_id, quota_gb):
    SWIFT_QUOTA_KEY = 'x-account-meta-quota-bytes'
    sclient = clients.get_swift_client(session, project_id=project_id)
    quota_bytes = quota_gb * 1024 * 1024 * 1024

    attempt = 1
    max_attempts = 10
    while attempt <= max_attempts:
        try:
            sclient.post_account(headers={SWIFT_QUOTA_KEY: quota_bytes})
        except Exception:
            LOG.warn("Failed to set swift quota,"
                     + " retying, attempt %s", attempt)
            time.sleep(attempt * 2)
            attempt += 1
            continue
        return
    LOG.error("Failed to set swift quota for project %s", project_id)


def send_welcome_email(user, project):
    data = {'user': user,
            'project': project,
            'expires': ''}
    body = flask.render_template("welcome_email.txt", **data)
    html = flask.render_template("welcome_email.html", **data)
    subject = "Welcome to NeCTAR Research Cloud - " \
              "Project Trial Allocation created"
    from_email = CONF.smtp.from_email

    email_utils.send_email(user.email, from_email, subject, body,
                           CONF.smtp.host, html)


def refresh_orcid(db_user):
    client = clients.get_orcid_client()
    try:
        orcid = client.search_by_email(db_user.email)
    except exceptions.HTTPError as e:
        LOG.error("Orcid refresh failed for user <User %s> (%s): url = %s",
                  db_user.id,
                  e.response.status_code,
                  e.request.url)
        LOG.exception(e)
        return False

    if orcid and orcid != db_user.orcid:
        if db_user.orcid:
            LOG.info("Changing orcid for <User %s>: %s -> %s",
                     db_user.id, db_user.orcid, orcid)
        else:
            LOG.info("Adding orcid for <User %s>: %s", db_user.id, orcid)
        db_user.orcid = orcid
        db.session.add(db_user)
        db.session.commit()
    elif orcid:
        LOG.info("Orcid has not changed for <User %s>: %s",
                 db_user.id, orcid)
    else:
        LOG.info("No orcid found for <User %s>", db_user.id)
    return True
