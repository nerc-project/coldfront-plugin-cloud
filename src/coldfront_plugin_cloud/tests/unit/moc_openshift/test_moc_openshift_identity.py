# pylint: disable=missing-module-docstring
from unittest import mock

import kubernetes.dynamic.exceptions as kexc


def test_qualified_id_user(moc):
    assert moc.qualified_id_user("foo") == "fake-id-provider:foo"


def test_get_identity(moc):
    fake_identity = mock.Mock(spec=["to_dict"])
    fake_identity.to_dict.return_value = {"id": "fake-id"}
    moc.client.resources.get.return_value.get.return_value = fake_identity
    res = moc.get_identity("fake-id")
    assert res == {"id": "fake-id"}


def test_identity_exists(moc):
    fake_identity = mock.Mock(spec=["to_dict"])
    fake_identity.to_dict.return_value = {"id": "fake-id"}
    moc.client.resources.get.return_value.get.return_value = fake_identity
    assert moc.identity_exists("fake-id")


def test_identity_exists_not(moc):
    moc.client.resources.get.return_value.get.side_effect = kexc.NotFoundError(
        mock.Mock()
    )
    assert not moc.identity_exists("fake-id")


def test_create_identity(moc):
    fake_identity = mock.Mock(spec=["to_dict"])
    fake_identity.to_dict.return_value = {"id": "fake-id"}
    moc.client.resources.get.return_value.create.return_value = fake_identity
    res = moc.create_identity("fake-id")
    assert res["id"] == "fake-id"
    moc.client.resources.get.return_value.create.assert_called_with(
        body={"providerName": "fake-id-provider", "providerUserName": "fake-id"}
    )


def test_delete_identity(moc):
    fake_identity = mock.Mock(spec=["to_dict"])
    fake_identity.to_dict.return_value = {}
    moc.client.resources.get.return_value.delete.return_value = fake_identity
    res = moc.delete_identity("fake-id")
    assert res == {}
    moc.client.resources.get.return_value.delete.assert_called_with(
        name="fake-id-provider:fake-id"
    )


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_user")
def test_useridentitymapping_exists(fake_get_user, moc):
    fake_get_user.return_value = {"identities": ["fake-id-provider:fake-id"]}
    assert moc.useridentitymapping_exists("fake-user", "fake-id")


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.get_user")
def test_useridentitymapping_exists_not(fake_get_user, moc):
    fake_get_user.side_effect = kexc.NotFoundError(mock.Mock())
    assert not moc.useridentitymapping_exists("fake-user", "fake-id")


def test_createuseridentitymapping(moc):
    fake_idm = mock.Mock(spec=["to_dict"])
    fake_idm.to_dict.return_value = {}
    moc.client.resources.get.return_value.create.return_value = fake_idm
    res = moc.create_useridentitymapping("fake-user", "fake-id")
    assert res == {}
    moc.client.resources.get.return_value.create.assert_called_with(
        body={
            "user": {"name": "fake-user"},
            "identity": {"name": "fake-id-provider:fake-id"},
        }
    )
