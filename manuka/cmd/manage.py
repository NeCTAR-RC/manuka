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

import click
import datetime
from flask.cli import FlaskGroup

from manuka import app
from manuka.extensions import db
from manuka import models


@click.group(cls=FlaskGroup, create_app=app.create_app)
def cli():
    """Management script for the Manuka application."""


@cli.command('add-domain-mapping')
@click.argument("domain")
@click.argument("idp")
def add_domain_mapping(domain, idp):
    """Adds a mapping for a domain and IdP"""

    mapping = db.session.query(models.DomainIdpMapping).filter_by(
        idp_entity_id=idp).first()
    if mapping:
        mapping.domain_id = domain
        mapping.last_seen = datetime.datetime.now()
    else:
        mapping = models.DomainIdpMapping(domain_id=domain,
                                          idp_entity_id=idp)
    db.session.add(mapping)
    db.session.commit()
