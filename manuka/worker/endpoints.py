from oslo_config import cfg
from oslo_log import log as logging


from manuka.worker import manager as worker_manager


CONF = cfg.CONF

LOG = logging.getLogger(__name__)


class Endpoints(object):

    # API version history:
    #   1.0 - Initial version.

    def __init__(self):
        self.manager = worker_manager.Manager()

    def create_user(self, ctxt, shib_user):
        self.manager.create_user(shib_user)
