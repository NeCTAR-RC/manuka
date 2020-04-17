#import flask

from manuka.api.v1.resources import user


#bp = flask.Blueprint('api_v1', __name__, url_prefix='/api/v1')


def initialize_resources(api):
    api.add_resource(user.UserList, '/api/v1/users/')
    api.add_resource(user.User, '/api/v1/users/<id>/')
