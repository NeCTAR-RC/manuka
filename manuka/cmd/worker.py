import sys

import cotyledon
from cotyledon import oslo_config_glue
from oslo_config import cfg

from manuka.common import service
from manuka.worker import consumer


CONF = cfg.CONF


def main():
    service.prepare_service(sys.argv)

    sm = cotyledon.ServiceManager()
    sm.add(consumer.ConsumerService, workers=CONF.worker.workers,
           args=(CONF,))
    oslo_config_glue.setup(sm, CONF, reload_method="mutate")
    sm.run()


if __name__ == "__main__":
    main()
