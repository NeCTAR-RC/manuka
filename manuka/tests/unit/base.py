from unittest import mock

import fixtures
import flask_testing
from oslo_config import cfg
import oslo_messaging as messaging
from oslo_messaging import conffixture as messaging_conffixture
import testtools


import manuka
from manuka.common import rpc
from manuka.extensions import db


class TestCase(flask_testing.TestCase):

    def create_app(self):
        return manuka.create_app({
            'SECRET_KEY': 'secret',
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': "sqlite://",
            'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        }, conf_file='manuka/tests/settings.conf')

    def setUp(self):
        super().setUp()
        self.addCleanup(mock.patch.stopall)
        db.create_all()

    def tearDown(self):
        super().tearDown()
        db.session.remove()
        db.drop_all()


class TestRpc(testtools.TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._buses = {}

    def _fake_create_transport(self, url):
        if url not in self._buses:
            self._buses[url] = messaging.get_rpc_transport(
                cfg.CONF,
                url=url)
        return self._buses[url]

    def setUp(self):
        super().setUp()
        self.addCleanup(rpc.cleanup)
        self.messaging_conf = messaging_conffixture.ConfFixture(cfg.CONF)
        self.messaging_conf.transport_url = 'fake:/'
        self.useFixture(self.messaging_conf)
        self.useFixture(fixtures.MonkeyPatch(
            'manuka.common.rpc.create_transport',
            self._fake_create_transport))
        with mock.patch('manuka.common.rpc.get_transport_url') as mock_gtu:
            mock_gtu.return_value = None
            rpc.init()
