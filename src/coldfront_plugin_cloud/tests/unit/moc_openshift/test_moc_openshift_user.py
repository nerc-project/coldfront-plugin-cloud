# pylint: disable=missing-module-docstring
from unittest import mock

import kubernetes.dynamic.exceptions as kexc


def test_get_user(moc):
    fake_user = mock.Mock(spec=["to_dict"])
    fake_user.to_dict.return_value = {"user": "fake_user"}
    moc.client.resources.get.return_value.get.return_value = fake_user
    res = moc.get_user("fake_user_name")
    assert res == {"user": "fake_user"}


def test_user_exists(moc):
    fake_user = mock.Mock(spec=["to_dict"])
    fake_user.to_dict.return_value = {"user": "fake_user"}
    moc.client.resources.get.return_value.get.return_value = fake_user
    res = moc.user_exists("fake_user_name")
    assert res


def test_user_exists_not(moc):
    moc.client.resources.get.return_value.get.side_effect = kexc.NotFoundError(
        mock.Mock()
    )
    res = moc.user_exists("fake_user_name")
    assert not res


def test_create_user(moc):
    fake_user = mock.Mock(spec=["to_dict"])
    fake_user.to_dict.return_value = {"user": "fake_user_name"}
    moc.client.resources.get.return_value.create.return_value = fake_user
    res = moc.create_user("fake_user_name", "Fake User")
    assert res["user"] == "fake_user_name"
    moc.client.resources.get.return_value.create.assert_called_with(
        body={"metadata": {"name": "fake_user_name"}, "fullName": "Fake User"}
    )


def test_delete_user(moc):
    fake_user = mock.Mock(spec=["to_dict"])
    fake_user.to_dict.return_value = {}
    moc.client.resources.get.return_value.delete.return_value = fake_user
    res = moc.delete_user("fake_user_name")
    assert res == {}
    moc.client.resources.get.return_value.delete.assert_called_with(
        name="fake_user_name"
    )
