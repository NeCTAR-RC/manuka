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

from manuka.api.v1.resources import base
from manuka.api.v1.schemas import terms as schemas
from manuka.extensions import db
from manuka import models


class TermsList(base.Resource):

    schema = schemas.terms

    def get(self, **kwargs):
        terms_list = db.session.query(models.Terms)
        return self.paginate(terms_list)


class Terms(base.Resource):

    schema = schemas.term

    def _get_terms(self, id):
        return db.session.query(models.Terms).filter_by(id=id).first_or_404()

    def get(self, id):
        term = self._get_terms(id)
        return self.schema.dump(term)


class CurrentTerms(Terms):

    schema = schemas.term

    def _get_terms(self):
        return db.session.query(models.Terms).order_by(
            models.Terms.issued.desc()).first_or_404()

    def get(self):
        term = self._get_terms()
        return self.schema.dump(term)
