import flask_migrate
import flask_sqlalchemy


db = flask_sqlalchemy.SQLAlchemy()
migrate = flask_migrate.Migrate()
