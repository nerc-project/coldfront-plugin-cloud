# pylint: disable=missing-module-docstring,wrong-import-position,redefined-outer-name

from unittest import mock

import logging
import pytest

from acct_mgt.moc_openshift import MocOpenShift4x


@pytest.fixture
def config():
    return {
        "IDENTITY_PROVIDER": "fake-id-provider",
        "QUOTA_DEF_FILE": "fake-quota-file",
        "LIMIT_DEF_FILE": "fake-limit-file",
    }


@pytest.fixture()
def moc(config):
    fake_client = mock.Mock(spec=["resources"])
    fake_logger = mock.Mock(spec=logging.Logger)
    return MocOpenShift4x(fake_client, fake_logger, config)
