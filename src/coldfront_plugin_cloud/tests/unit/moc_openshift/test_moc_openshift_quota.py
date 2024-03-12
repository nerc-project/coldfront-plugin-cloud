# pylint: disable=missing-module-docstring
from unittest import mock

import json
import pytest


@pytest.mark.xfail(reason="raises FileNotFoundError")
def test_get_quota_definitions_missing(moc):
    """What happens if the quota file is missing?"""
    with mock.patch("builtins.open", mock.mock_open()) as fake_open:
        fake_open.side_effect = FileNotFoundError()
        res = moc.get_quota_definitions()
        assert res == {}


@pytest.mark.xfail(reason="raises JSONDecodeError")
def test_get_quota_definitions_empty(moc):
    """What happens if the quota file exists but is empty?"""
    with mock.patch("builtins.open", mock.mock_open(read_data="")):
        res = moc.get_quota_definitions()
        assert res == {}


@pytest.mark.xfail(reason="raises TypeError")
def test_get_quota_definitions_invalid(moc):
    """What happens if the quota file exists but contains invalid data?"""
    with mock.patch("builtins.open", mock.mock_open(read_data='{"foo": "bar"}')):
        res = moc.get_quota_definitions()
        assert res == {}


def test_get_quota_definitions_valid(moc):
    """What happens if a valid quota file exists?"""
    quotadefs = {
        ":configmaps": {"base": 2, "coefficient": 0},
    }
    with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(quotadefs))):
        res = moc.get_quota_definitions()
        quotadefs[":configmaps"]["value"] = None
        assert res == quotadefs


def test_split_quota_name(moc):
    assert moc.split_quota_name(":foo") == ("Project", "foo")
    assert moc.split_quota_name("scope:foo") == ("scope", "foo")


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_project", mock.Mock())
def test_get_resourcequotas(moc):
    fake_quota = mock.Mock(spec=["to_dict"])
    fake_quota.to_dict.return_value = {"items": []}
    moc.client.resources.get.return_value.get.return_value = fake_quota
    res = moc.get_resourcequotas("fake-project")
    moc.client.resources.get.return_value.get.assert_called()
    assert res == []


def test_delete_quota(moc):
    fake_quota = mock.Mock(spec=["to_dict"])
    fake_quota.to_dict.return_value = {}
    moc.client.resources.get.return_value.delete.return_value = fake_quota
    res = moc.delete_resourcequota("test-project", "test-quota")
    moc.client.resources.get.return_value.delete.assert_called()
    assert res == {}


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_resourcequotas")
def test_delete_moc_quota(fake_get_resourcequotas, moc):
    fake_get_resourcequotas.return_value = [{"metadata": {"name": "fake-quota"}}]
    moc.delete_moc_quota("test-project")
    moc.client.resources.get.return_value.delete.assert_any_call(
        namespace="test-project", name="fake-quota"
    )


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_resourcequotas")
def test_get_moc_quota_from_resourcequotas(fake_get_resourcequotas, moc):
    fake_get_resourcequotas.return_value = [
        {
            "metadata": {"name": "fake-quota"},
            "spec": {"hard": {"cpu": "1"}},
        },
        {
            "metadata": {"name": "fake-quota"},
            "spec": {"hard": {"memory": "1"}, "scopes": ["BestEffort"]},
        },
    ]

    res = moc.get_moc_quota_from_resourcequotas("test_project")
    assert res == {":cpu": "1", "BestEffort:memory": "1"}


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.wait_for_quota_to_settle")
def test_create_shift_quotas(fake_wait_quota, moc):
    quotadefs = {
        ":configmaps": {"value": "1"},
        ":cpu": {"value": "1"},
        ":resourcequotas": {"value": "1"},
    }

    moc.client.resources.get.return_value.create.return_value = mock.Mock()

    moc.create_shift_quotas("fake-project", quotadefs)

    moc.client.resources.get.return_value.create.assert_called_with(
        namespace="fake-project",
        body={
            "metadata": {"name": "fake-project-project"},
            "spec": {"hard": {"configmaps": "1", "cpu": "1", "resourcequotas": "1"}},
        },
    )

    fake_wait_quota.assert_called()


def test_wait_for_quota_to_settle(moc):
    fake_quota = mock.Mock(spec=["to_dict"])
    fake_quota.to_dict.return_value = {
        "metadata": {"name": "fake-quota"},
        "spec": {"hard": {"resourcequotas": "1"}},
        "status": {"used": {"resourcequotas": "1"}},
    }
    moc.client.resources.get.return_value.get.return_value = fake_quota

    moc.wait_for_quota_to_settle("fake-project", fake_quota.to_dict())

    moc.client.resources.get.return_value.get.assert_called_with(
        namespace="fake-project",
        name="fake-quota",
    )


@mock.patch(
    "acct_mgt.moc_openshift.MocOpenShift4x.get_moc_quota_from_resourcequotas",
    mock.Mock(),
)
@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.delete_moc_quota", mock.Mock())
@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.create_shift_quotas")
def test_update_moc_quota(
    fake_create_quotas,
    moc,
):
    quotadefs = {
        ":configmaps": {},
        ":cpu": {},
    }

    new_quota = {
        "Quota": {
            ":cpu": "1000",
        }
    }

    with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(quotadefs))):
        moc.update_moc_quota("fake-project", new_quota)
        fake_create_quotas.assert_called_with(
            "fake-project",
            {":configmaps": {"value": None}, ":cpu": {"value": "1000"}},
        )


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.delete_moc_quota", mock.Mock())
@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_resourcequotas")
@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.create_shift_quotas")
def test_update_moc_quota_patch(
    fake_create_quotas,
    fake_get_resourcequotas,
    moc,
):
    fake_quota = {
        "metadata": {"name": "fake-quota"},
        "spec": {
            "hard": {"services": "2"},
        },
    }

    quotadefs = {
        ":configmaps": {},
        ":cpu": {},
    }

    new_quota = {
        "Quota": {
            ":cpu": "1000",
        }
    }

    fake_get_resourcequotas.return_value = [fake_quota]

    with mock.patch("builtins.open", mock.mock_open(read_data=json.dumps(quotadefs))):
        moc.update_moc_quota("fake-project", new_quota, patch=True)
        fake_create_quotas.assert_called_with(
            "fake-project",
            {
                ":services": {"value": "2"},
                ":configmaps": {"value": None},
                ":cpu": {"value": "1000"},
            },
        )


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_moc_quota_from_resourcequotas")
def test_get_moc_quota(fake_get_quota, moc):
    fake_get_quota.return_value = {
        ":services": {"value": "2"},
        ":configmaps": {"value": None},
        ":cpu": {"value": "1000"},
    }
    res = moc.get_moc_quota("fake-project")
    assert res == {
        "Version": "0.9",
        "Kind": "MocQuota",
        "ProjectName": "fake-project",
        "Quota": {
            ":services": {"value": "2"},
            ":configmaps": {"value": None},
            ":cpu": {"value": "1000"},
        },
    }


def test_get_limit_definitions_valid(moc):
    with mock.patch("builtins.open", mock.mock_open(read_data="{}")):
        res = moc.get_limit_definitions()
        assert res == {}


def test_create_limits(moc):
    limitdefs = '[{"type": "Container", "default": {"cpu": "200m", "memory": "512Mi"}}]'
    fake_limit = mock.Mock(spec=["to_dict"])
    fake_limit.to_dict.return_value = "fake-limit"
    moc.client.resources.get.return_value.create.return_value = fake_limit
    with mock.patch("builtins.open", mock.mock_open(read_data=limitdefs)):
        res = moc.create_limits("fake-project")
        assert res == "fake-limit"
        moc.client.resources.get.return_value.create.assert_called_with(
            namespace="fake-project",
            body={
                "metadata": {"name": "fake-project-limits"},
                "spec": {"limits": json.loads(limitdefs)},
            },
        )


def test_create_limits_custom(moc):
    with mock.patch("builtins.open", mock.mock_open()):
        moc.create_limits("fake-project", limits="fake-limits")
        moc.client.resources.get.return_value.create.assert_called_with(
            namespace="fake-project",
            body={
                "metadata": {"name": "fake-project-limits"},
                "spec": {"limits": "fake-limits"},
            },
        )
