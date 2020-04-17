
from manuka.api.v1.resources import base
from manuka.api.v1.schemas import user
from manuka.extensions import db
from manuka import models
from manuka import policy


enforcer = policy.get_enforcer()


class UserList(base.Resource):

    def get(self):
        db_users = db.session.query(models.User).all()
        return user.users_schema.dump(db_users)


class User(base.Resource):

    def get(self, id):
        target = {'user_id': id}
        enforcer.authorize(action, target, context)
        db_user = db.session.query(models.User).filter_by(id=id).first()
        return user.user_schema.dump(db_user)
