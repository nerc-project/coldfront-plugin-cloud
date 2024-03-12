# pylint: disable=missing-module-docstring
from unittest import mock

import pytest

from acct_mgt.moc_openshift import MocOpenShift4x


def test_moc_openshift(moc):
    assert moc.id_provider == "fake-id-provider"
    assert moc.quotafile == "fake-quota-file"
    assert moc.limitfile == "fake-limit-file"


def test_moc_openshift_no_limit():
    with pytest.raises(SystemExit):
        MocOpenShift4x(
            mock.Mock(),
            mock.Mock(),
            {
                "IDENTITY_PROVIDER": "fake",
                "QUOTA_DEF_FILE": "fake",
                "LIMIT_DEF_FILE": None,
            },
        )


@pytest.mark.xfail(reason="bug")
def test_moc_openshift_no_quota():
    with pytest.raises(SystemExit):
        MocOpenShift4x(
            mock.Mock(),
            mock.Mock(),
            {
                "IDENTITY_PROVIDER": "fake",
                "QUOTA_DEF_FILE": None,
                "LIMIT_DEF_FILE": "fake",
            },
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
