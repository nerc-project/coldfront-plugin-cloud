# pylint: disable=missing-module-docstring,wrong-import-position,redefined-outer-name

from unittest import mock

import logging
import pytest

from coldfront_plugin_cloud.acct_mgt.moc_openshift import MocOpenShift4x

@pytest.fixture
def config():
    return {
        "identity_name": "fake-id-provider",
        "quotas": {
            ":requests.fake1": {"base": 2, "coefficient": 0},
            ":requests.fake2": {"base": 2, "coefficient": 0}
        },
        "limits": {
            "type": "FakeContainer",
            "default": {"cpu": "2", "memory": "1024Mi", "nvidia.com/gpu": "0"}
        },
    }


@pytest.fixture()
def moc(config):
    fake_client = mock.Mock(spec=["resources"])
    fake_logger = mock.Mock(spec=logging.Logger)
    return MocOpenShift4x(fake_client, fake_logger, **config)
