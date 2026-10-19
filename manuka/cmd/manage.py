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

import csv
import datetime

import click
from flask.cli import FlaskGroup

from manuka import app
from manuka.extensions import db
from manuka import models


@click.group(cls=FlaskGroup, create_app=app.create_app)
def cli():
    """Management script for the Manuka application."""


@cli.command("add-domain-mapping")
@click.argument("domain")
@click.argument("idp")
def add_domain_mapping(domain, idp):
    """Adds a mapping for a domain and SAML IdP entityID.

    OpenID Connect logins are mapped by [oidc] federation_domains
    instead.
    """

    mapping = (
        db.session.query(models.DomainIdpMapping)
        .filter_by(idp_entity_id=idp)
        .first()
    )
    if mapping:
        mapping.domain_id = domain
        mapping.last_seen = datetime.datetime.now()
    else:
        mapping = models.DomainIdpMapping(domain_id=domain, idp_entity_id=idp)
    db.session.add(mapping)
    db.session.commit()


@cli.command("oidc-migration-report")
@click.option(
    "--days",
    default=180,
    show_default=True,
    help="Count users who logged in within this many days as active.",
)
@click.option(
    "--bucket",
    type=click.Choice(models.MIGRATION_BUCKETS),
    default="action",
    show_default=True,
    help="Which group of users to list.",
)
@click.option("--summary", is_flag=True, help="Print the group sizes only.")
def oidc_migration_report(days, bucket, summary):
    """Report how active users will reach the OpenID Connect login.

    Groups: linked (already using it), auto (will link on first use
    through a strong identifier) and action (must link before
    Shibboleth is switched off). Lists one group as CSV on stdout, with
    the SAML IdP of each user for per-institution follow-up.
    """
    since = datetime.datetime.now() - datetime.timedelta(days=days)
    report = models.oidc_migration_report(since)
    if summary:
        for name in models.MIGRATION_BUCKETS:
            click.echo(f"{name}: {len(report[name])}")
        return

    writer = csv.writer(click.get_text_stream("stdout"))
    writer.writerow(
        ["keystone_user_id", "email", "displayname", "last_login", "saml_idp"]
    )
    for user in report[bucket]:
        saml_idp = next(
            (
                external_id.idp
                for external_id in user.external_ids
                if external_id.protocol == models.PROTOCOL_SAML
            ),
            "",
        )
        writer.writerow(
            [
                user.keystone_user_id,
                user.email,
                user.displayname,
                user.last_login.isoformat() if user.last_login else "",
                saml_idp or "",
            ]
        )
