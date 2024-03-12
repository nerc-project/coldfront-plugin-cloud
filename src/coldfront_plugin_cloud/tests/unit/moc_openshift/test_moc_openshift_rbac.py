# pylint: disable=missing-module-docstring
from unittest import mock

import pytest

import kubernetes.dynamic.exceptions as kexc


def test_user_rolebinding_exists_invalid_role(moc):
    with pytest.raises(ValueError):
        moc.user_rolebinding_exists("fake-user", "fake-project", "invalid-role")


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_rolebindings")
def test_user_rolebinding_exists_not(fake_get_rb, moc):
    fake_get_rb.side_effect = kexc.NotFoundError(mock.Mock())
    assert not moc.user_rolebinding_exists("fake-user", "fake-project", "admin")


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_rolebindings")
def test_user_rolebinding_exists(fake_get_rb, moc):
    fake_get_rb.return_value = {
        "subjects": [
            {
                "kind": "User",
                "name": "fake-user",
            }
        ],
    }

    assert moc.user_rolebinding_exists("fake-user", "fake-project", "admin")


def test_add_user_to_role_invalid_role(moc):
    with pytest.raises(ValueError):
        moc.add_user_to_role("fake-project", "fake-user", "invalid-role")


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_rolebindings")
@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.update_rolebindings")
def test_add_user_to_role(fake_update_rb, fake_get_rb, moc):
    fake_get_rb.return_value = {
        "subjects": [],
    }

    moc.add_user_to_role("fake-project", "fake-user", "admin")
    fake_update_rb.assert_called_with(
        "fake-project", {"subjects": [{"kind": "User", "name": "fake-user"}]}
    )


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_rolebindings")
@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.create_rolebindings")
def test_add_user_to_role_not_exists(fake_create_rb, fake_get_rb, moc):
    fake_get_rb.side_effect = kexc.NotFoundError(mock.Mock())

    moc.add_user_to_role("fake-project", "fake-user", "admin")
    fake_create_rb.assert_called_with("fake-project", "fake-user", "admin")


def test_remove_user_from_role_invalid_role(moc):
    with pytest.raises(ValueError):
        moc.remove_user_from_role("fake-project", "fake-user", "invalid-role")


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_rolebindings")
def test_remove_user_from_role(fake_get_rb, moc):
    fake_get_rb.return_value = {
        "subjects": [{"kind": "User", "name": "fake-user"}],
    }
    moc.remove_user_from_role("fake-project", "fake-user", "admin")
    moc.client.resources.get.return_value.patch.assert_called_with(
        body={"subjects": []}, namespace="fake-project"
    )


def test_remove_user_from_role_not_exists(moc):
    moc.client.resources.get.return_value.get.side_effect = kexc.NotFoundError(
        mock.Mock()
    )
    moc.remove_user_from_role("fake-project", "fake-user", "admin")
    moc.client.resources.get.return_value.patch.assert_not_called()


def test_get_rolebindings(moc):
    fake_rb = mock.Mock(spec=["to_dict"])
    fake_rb.to_dict.return_value = {"subjects": []}
    moc.client.resources.get.return_value.get.return_value = fake_rb
    res = moc.get_rolebindings("fake-project", "admin")
    assert res == fake_rb.to_dict()


def test_get_rolebindings_no_subjects(moc):
    fake_rb = mock.Mock(spec=["to_dict"])
    fake_rb.to_dict.return_value = {}
    moc.client.resources.get.return_value.get.return_value = fake_rb
    res = moc.get_rolebindings("fake-project", "admin")
    assert res == {"subjects": []}


def test_list_rolebindings(moc):
    fake_rb = mock.Mock(spec=["to_dict"])
    fake_rb.to_dict.return_value = {
        "items": ["rb1", "rb2"],
    }
    moc.client.resources.get.return_value.get.return_value = fake_rb

    res = moc.list_rolebindings("fake-project")
    assert res == ["rb1", "rb2"]


def test_list_rolebindings_not_exists(moc):
    moc.client.resources.get.return_value.get.side_effect = kexc.NotFoundError(
        mock.Mock()
    )

    res = moc.list_rolebindings("fake-project")
    assert res == []


def test_create_rolebindings(moc):
    fake_rb = mock.Mock(spec=["to_dict"])
    fake_rb.to_dict.return_value = {}
    moc.client.resources.get.return_value.create.return_value = fake_rb
    res = moc.create_rolebindings("fake-project", "fake-user", "admin")
    assert res == {}
    moc.client.resources.get.return_value.create.assert_called_with(
        namespace="fake-project",
        body={
            "metadata": {"name": "admin", "namespace": "fake-project"},
            "subjects": [{"name": "fake-user", "kind": "User"}],
            "roleRef": {"name": "admin", "kind": "ClusterRole"},
        },
    )
