from manuka.extensions import ma
from manuka import models


class UserSchema(ma.SQLAlchemySchema):

    class Meta:
        model = models.User
        fields = ('id', 'displayname', 'email', 'state', 'registered_at',
                  'last_login', 'terms_accepted_at', 'home_organization',
                  'orcid', 'affiliation'
        )


user_schema = UserSchema()
users_schema = UserSchema(many=True)
