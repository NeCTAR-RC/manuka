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
# This contains an ad hoc function backfilling ORCIDs from a CSV file
#
# It depends on manukaclient, an OS_* environment variables
#
# Input is a CSV (delimiter=',') with no header.  Each line is an email
# address followed by an ORCID.
#

import csv
import logging
import os

from keystoneauth1 import loading
from keystoneauth1 import session

from manukaclient import client

LOG = logging.getLogger(__name__)

AUTH_URL = os.environ.get("OS_AUTH_URL")
USERNAME = os.environ.get("OS_USERNAME")
PASSWORD = os.environ.get("OS_PASSWORD")
PROJECT_NAME = os.environ.get("OS_PROJECT_NAME")


def backfill(csv_filename):
    loader = loading.get_plugin_loader('password')
    auth = loader.load_from_options(auth_url=AUTH_URL,
                                    username=USERNAME,
                                    password=PASSWORD,
                                    project_name=PROJECT_NAME,
                                    user_domain_id='default',
                                    project_domain_id='default')
    sess = session.Session(auth=auth)
    mc = client.Client("1", session=sess)

    with open(csv_filename, 'r') as csv_file:
        reader = csv.reader(csv_file, delimiter=',', skipinitialspace=True)
        for row in reader:
            email = row[0]
            orcid = row[1]
            users = mc.users.search(email)
            if len(users) != 1:
                # insert Highlander quote here
                raise Exception("Manuka search(%s) -> %s" % (email, users))

            print("%s -> %s" % (email, users[0].id))
            mc.users.update(users[0].id, orcid=orcid)
