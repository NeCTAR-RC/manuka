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

import re

from oslo_config import cfg
from oslo_log import log as logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from manuka import config

from manuka.common import orcid_client
from manuka.models import User

LOG = logging.getLogger(__name__)


def backfill(config_file="/home/ubuntu/manuka.conf"):
    config.init(args=[], conf_file=config_file)
    client = orcid_client.Client()
    engine = create_engine(cfg.CONF.database.connection)
    Session = sessionmaker(bind=engine)
    session = Session()

    pat = re.compile("^[a-zA-Z0-9_.-]+@[a-zA-Z0-9_.-]+$")
    for user in session.query(User).order_by(User.registered_at).all():
        email = str(user.email)
        surname = str(user.surname)
        first_name = str(user.first_name)
        if pat.match(email):
            orcid = client.search_by_email(email)
            print("%s -> %s (%s)" % (email, orcid, user.orcid))
            orcid = client.search_by_names(surname, first_name)
            print("%s, %s -> %s" % (surname, first_name, orcid))


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
