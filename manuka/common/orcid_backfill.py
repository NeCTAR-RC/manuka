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

    pat = re.compile("^([a-zA-Z0-9_\\-\\.]+)@"
                     "([a-zA-Z0-9_\\-\\.]+)\\.([a-zA-Z]{2,5})$")
    for user in session.query(User).order_by(User.registered_at).all():
        email = str(user.email)
        if pat.match(email):
            print("%s -> %s" % (email, client.search_by_email(email)))
