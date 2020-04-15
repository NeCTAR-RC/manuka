from oslo_config import cfg
from oslo_log import log as logging
import oslo_messaging as messaging
from oslo_messaging.rpc import dispatcher

LOG = logging.getLogger(__name__)

TRANSPORT = None


def init():
    global TRANSPORT
    TRANSPORT = create_transport(get_transport_url())


def cleanup():
    global TRANSPORT
    if TRANSPORT is not None:
        TRANSPORT.cleanup()
        TRANSPORT = None


def get_transport_url(url_str=None):
    return messaging.TransportURL.parse(cfg.CONF, url_str)


def get_client(target, version_cap=None, serializer=None,
               call_monitor_timeout=None):
    if TRANSPORT is None:
        init()

    return messaging.RPCClient(TRANSPORT,
                               target,
                               version_cap=version_cap,
                               serializer=serializer,
                               call_monitor_timeout=call_monitor_timeout)


def get_server(target, endpoints, executor='threading',
               access_policy=dispatcher.DefaultRPCAccessPolicy,
               serializer=None):
    if TRANSPORT is None:
        init()

    return messaging.get_rpc_server(TRANSPORT,
                                    target,
                                    endpoints,
                                    executor=executor,
                                    serializer=serializer,
                                    access_policy=access_policy)


def create_transport(url):
    return messaging.get_rpc_transport(cfg.CONF, url=url)
