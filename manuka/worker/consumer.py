import cotyledon
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_messaging.rpc import dispatcher

from manuka.common import rpc
from manuka.worker import endpoints


LOG = logging.getLogger(__name__)


class ConsumerService(cotyledon.Service):

    def __init__(self, worker_id, conf):
        super(ConsumerService, self).__init__(worker_id)
        self.conf = conf
        self.topic = 'manuka-worker'
        self.server = conf.host
        self.endpoints = []
        self.access_policy = dispatcher.DefaultRPCAccessPolicy
        self.message_listener = None

    def run(self):
        LOG.info('Starting consumer...')
        target = messaging.Target(topic=self.topic, server=self.server,
                                  fanout=False, version='1.0')
        self.endpoints = [endpoints.Endpoints()]
        self.message_listener = rpc.get_server(
            target, self.endpoints,
            executor='threading',
            access_policy=self.access_policy
        )
        self.message_listener.start()

    def terminate(self):
        if self.message_listener:
            LOG.info('Stopping consumer...')
            self.message_listener.stop()

            LOG.info('Consumer successfully stopped.  Waiting for '
                     'final messages to be processed...')
            self.message_listener.wait()
        if self.endpoints:
            LOG.info('Shutting down endpoint worker executors...')
            for e in self.endpoints:
                try:
                    e.worker.executor.shutdown()
                except AttributeError:
                    pass
        super(ConsumerService, self).terminate()
