import oslo_messaging

from manuka.common import rpc


class WorkerAPI(object):

    def __init__(self):
        target = oslo_messaging.Target(topic='manuka-worker', version='1.0')
        self._client = oslo_messaging.RPCClient(rpc.TRANSPORT, target)

    def create_user(self, ctxt, shib_user):
        cctxt = self._client.prepare(version='1.0')
        cctxt.cast(ctxt, 'create_user', shib_user=shib_user)
