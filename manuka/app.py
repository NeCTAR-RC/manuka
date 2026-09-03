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

import os

from beaker import middleware as beaker
import flask
from oslo_config import cfg
from oslo_log import log as logging
from oslo_middleware import healthcheck
from oslo_middleware import http_proxy_to_wsgi
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from manuka.common import sentry
from manuka import config
from manuka import extensions


CONF = cfg.CONF
LOG = logging.getLogger(__name__)


def create_app(test_config=None, conf_file=None, init_config=True):
    # create and configure the app
    if init_config:
        if conf_file:
            config.init(conf_file=conf_file)
        else:
            config.init()
    app = flask.Flask(__name__)
    if test_config is None:
        app.config.from_mapping(
            SECRET_KEY=CONF.flask.secret_key,
            SQLALCHEMY_DATABASE_URI=CONF.database.connection,
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            SQLALCHEMY_ENGINE_OPTIONS={
                "pool_pre_ping": True,
                "pool_recycle": CONF.database.connection_recycle_time,
            },
        )
    else:
        app.config.update(test_config)

    config.setup_logging(CONF)
    if init_config:
        sentry.setup()
    api_bp = flask.Blueprint("api", __name__, url_prefix="/api")
    register_extensions(app, api_bp)
    register_resources(extensions.api)
    register_blueprints(app)
    app.register_blueprint(api_bp)
    # ensure the instance folder exists
    try:
        os.makedirs(app.instance_path)
    except OSError:
        pass

    if CONF.fake_shib:
        from manuka import shib_faker

        app.wsgi_app = shib_faker.FakeShibboleth(app.wsgi_app)
        app.wsgi_app = beaker.SessionMiddleware(app.wsgi_app)

    app.wsgi_app = DispatcherMiddleware(
        app.wsgi_app, {"/healthcheck": healthcheck.Healthcheck(None)}
    )
    app.wsgi_app = http_proxy_to_wsgi.HTTPProxyToWSGI(app.wsgi_app)

    if CONF.auth_strategy == "keystone":
        from manuka.common import keystone

        app.wsgi_app = keystone.KeystoneContext(app.wsgi_app)
        app.wsgi_app = keystone.SkippingAuthProtocol(app.wsgi_app, {})
    from manuka.common import rpc

    rpc.init()

    return app


def register_extensions(app, api_bp):
    """Register Flask extensions."""
    extensions.api.init_app(api_bp)
    extensions.db.init_app(app)
    extensions.migrate.init_app(
        app, extensions.db, directory=os.path.join(app.root_path, "migrations")
    )
    extensions.ma.init_app(app)


def register_blueprints(app):
    from manuka import views

    app.register_blueprint(views.default_bp)
    app.register_blueprint(views.login_bp)


def register_resources(api):
    from manuka.api import v1 as api_v1

    api_v1.initialize_resources(api)
