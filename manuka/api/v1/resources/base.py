import flask
import flask_restful


AUTH_CONTEXT_ENV = 'auth'
REQUEST_CONTEXT_ENV = 'oslo_context'


class Resource(flask_restful.Resource):

    @property
    def auth_context(self):
        return flask.request.environ.get(AUTH_CONTEXT_ENV, None)

    @property
    def oslo_context(self):
        return flask.request.environ.get(REQUEST_CONTEXT_ENV, None)
