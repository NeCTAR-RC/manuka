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

#
# README
#
# These are some ad hoc functions for 1) extracting ORCIDs via email ->
# ORCID lookup, and 2) trying to figure out what proportion of Nectar
# users actually have ORCIDs.
#
# They read from the "rcshibboleth" database, but don't update it.
# You need to provide a 'manuka.conf' file with the database connection
# URL and an ORCID API key and secret.
#
# This depends on the 'manuka' module.

import re

from oslo_config import cfg
from oslo_log import log as logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from manuka import config

from manuka.common import orcid_client
from manuka.models import User

LOG = logging.getLogger(__name__)


def extract(config_file="/home/ubuntu/manuka.conf", skip_to=None):
    config.init(args=[], conf_file=config_file)
    client = orcid_client.Client()
    engine = create_engine(cfg.CONF.database.connection)
    Session = sessionmaker(bind=engine)
    session = Session()

    pat = re.compile("^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$")
    marker = skip_to
    scanned = 0
    skipped = 0
    for user in session.query(User).order_by(User.registered_at).all():
        email = str(user.email)
        if marker:
            if marker == email:
                print("finished skipping", flush=True)
                marker = None
            skipped += 1
            continue
        scanned += 1
        if pat.match(email):
            orcid = client.search_by_email(email)
            if orcid and not user.orcid:
                print ("%s, %s" % (email, orcid), flush=True)
    print("completed: scanned %s accounts, skipped %s accounts" %
          (scanned, skipped), flush=True)

def stats(config_file="/home/ubuntu/manuka.conf", limit=None):
    config.init(args=[], conf_file=config_file)
    client = orcid_client.Client()
    engine = create_engine(cfg.CONF.database.connection)
    Session = sessionmaker(bind=engine)
    session = Session()

    count = 0
    bogus = 0
    has_orcid = 0
    may_have_orcid = 0
    multiple_orcids = 0
    no_orcids = 0

    pat = re.compile("^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$")
    for user in session.query(User).order_by(User.registered_at).all():
        email = str(user.email)
        surname = str(user.surname)
        first_name = str(user.first_name)
        if pat.match(email):
            if client.search_by_email(email):
                has_orcid += 1
            else:
                orcids = client.search_by_names(surname, first_name)
                if len(orcids) == 0:
                    no_orcids += 1
                elif len(orcids) == 1:
                    may_have_orcid += 1
                else:
                    multiple_orcids += 1
        else:
            bogus += 1

        count += 1
        if limit and count >= limit:
            print("Reached the limit")
            break

    print("Total accounts analysed: ", count)
    print("Accounts with orcids (via email): ", has_orcid)
    print("Accounts with no orcid matches: ", no_orcids)
    print("Accounts with a possible orcid: ", may_have_orcid)
    print("Accounts with multiple possible orcids: ", multiple_orcids)
    print("Accounts with bogus emails: ", bogus)
