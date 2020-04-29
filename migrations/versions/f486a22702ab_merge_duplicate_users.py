"""merge duplicate users

Revision ID: f486a22702ab
Revises: 53c5ca8ba141
Create Date: 2020-04-29 16:04:01.980472

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base


# revision identifiers, used by Alembic.
revision = 'f486a22702ab'
down_revision = '53c5ca8ba141'
branch_labels = None
depends_on = None

Base = declarative_base()


class User(Base):
    __tablename__ = 'user'
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.String(64))
    last_login = sa.Column(sa.DateTime())
    terms_accepted_at = sa.Column(sa.DateTime())
    external_ids = relationship("ExternalId", back_populates="user")

    def __str__(self):
        return "<User %s>" % self.id


class ExternalId(Base):
    __tablename__ = 'external_id'
    id = sa.Column(sa.Integer, primary_key=True)
    user_id = sa.Column(sa.Integer, sa.ForeignKey(User.id))
    user = relationship("User", back_populates="external_ids")
    persistent_id = sa.Column(sa.String(250), unique=True)
    attributes = sa.Column(sa.JSON)


def upgrade():
    session = sa.orm.Session(bind=op.get_bind())
    for user in session.query(User).filter(User.user_id != None):
        primary_user = None
        same_user_id = session.query(User) \
                              .filter_by(user_id=user.user_id) \
                              .filter(User.user_id != None) \
                              .order_by(User.last_login.desc(),
                                        User.terms_accepted_at.desc(),
                              ).all()

        if len(same_user_id) == 1:
            continue
        primary_user = same_user_id[0]
        if user == primary_user:
            continue

        print("Merging user %s with %s - last-login %s" % (
                user, primary_user, primary_user.last_login))
        for eid in user.external_ids:
            eid.user_id = primary_user.id
            session.add(eid)
        session.delete(user)
        session.commit()

    op.create_unique_constraint(None, 'user', ['user_id'])


def downgrade():
    print("Unable to downgrade data migration")
    op.drop_constraint(None, 'user', type_='unique')
