# pylint: disable=missing-module-docstring
from unittest import mock

import pytest

from coldfront_plugin_cloud.acct_mgt.moc_openshift import MocOpenShift4x


def test_moc_openshift(moc):
    assert moc.id_provider == "fake-id-provider"
    assert moc.quotas == {
        ":requests.fake1": {"base": 2, "coefficient": 0},
        ":requests.fake2": {"base": 2, "coefficient": 0}
    }
    assert moc.limits == {
        "type": "FakeContainer",
        "default": {"cpu": "2", "memory": "1024Mi", "nvidia.com/gpu": "0"}
    }


def test_moc_openshift_no_limit():
    with pytest.raises(SystemExit):
        MocOpenShift4x(
            mock.Mock(),
            mock.Mock(),
            **{
                "identity_name": "fake-id-provider",
                "quotas": "fake-quota-file",
                "limits": None,
            }
        )


@pytest.mark.xfail(reason="bug")
def test_moc_openshift_no_quota():
    with pytest.raises(SystemExit):
        MocOpenShift4x(
            mock.Mock(),
            mock.Mock(),
            **{
                "identity_name": "fake-id-provider",
                "quotas": None,
                "limits": {"fake-limits": 1},
            }
        )


def test_split_quota_name(moc):
    assert moc.split_quota_name(":fake") == ("Project", "fake")
    assert moc.split_quota_name("scope:fake") == ("scope", "fake")


@pytest.mark.parametrize(
    "orig,expected",
    [
        ("fake", "fake"),
        ("  fake fake  ", "fake-fake"),
        ("This Is My Project!", "this-is-my-project"),
        ("Ñaño 1234", "a-o-1234"),
    ],
)
def test_cnvt_project_name(moc, orig, expected):
    assert moc.cnvt_project_name(orig) == expected


def test_get_resource_api_cached(moc):
    moc.apis = {"fake-apiversion:fake-kind": "fake-resource-api"}
    res = moc.get_resource_api("fake-apiversion", "fake-kind")
    assert res == "fake-resource-api"


def test_get_resource_api_new(moc):
    moc.client.resources.get.return_value = "fake-resource-api"
    res = moc.get_resource_api("fake-apiversion", "fake-kind")
    assert res == "fake-resource-api"
    assert "fake-apiversion:fake-kind" in moc.apis
