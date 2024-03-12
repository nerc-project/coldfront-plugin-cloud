# pylint: disable=missing-module-docstring
from unittest import mock

import pytest

import kubernetes.dynamic.exceptions as kexc


def test_get_project(moc):
    fake_project = mock.Mock(spec=["to_dict"])
    fake_project.to_dict.return_value = {"project": "fake-project"}
    moc.client.resources.get.return_value.get.return_value = fake_project
    res = moc.get_project("fake-project")
    assert res == {"project": "fake-project"}


def test_project_exists(moc):
    fake_project = mock.Mock()
    fake_project.to_dict.return_value = {}
    moc.client.resources.get.return_value.get.return_value = fake_project
    assert moc.project_exists("fake-project")


def test_project_exists_not(moc):
    moc.client.resources.get.return_value.get.side_effect = kexc.NotFoundError(
        mock.Mock()
    )
    assert not moc.project_exists("fake-project")


@mock.patch("acct_mgt.moc_openshift.MocOpenShift4x.create_limits", mock.Mock())
def test_create_project(moc):
    moc.create_project("fake-project", "Fake Project", "fake-user")
    moc.client.resources.get.return_value.create.assert_called_with(
        body={
            "metadata": {
                "name": "fake-project",
                "annotations": {
                    "openshift.io/display-name": "Fake Project",
                    "openshift.io/requester": "fake-user",
                },
                "labels": {"nerc.mghpcc.org/project": "true"},
            }
        }
    )


def test_delete_project(moc):
    moc.delete_project("fake-project")
    moc.client.resources.get.return_value.delete.assert_called_with(name="fake-project")


def test_get_users_in_project_with_nonexistent_project(moc):
    moc.client.resources.get.return_value.get.side_effect = kexc.NotFoundError(
        mock.Mock()
    )

    with pytest.raises(kexc.NotFoundError):
        moc.get_users_in_project("nonexistent_project")


def test_get_users_in_project_with_no_rolebindings(moc):
    dummy_project = {"name": "project1"}
    moc.get_project = mock.Mock(return_value=dummy_project)

    moc.get_rolebindings = mock.Mock(side_effect=kexc.NotFoundError(mock.Mock()))

    users = moc.get_users_in_project("project1")

    assert users == []


def test_get_users_in_project_with_project_with_one_rolebinding(moc):
    dummy_project = {"name": "project1"}
    moc.get_project = mock.Mock(return_value=dummy_project)

    # pylint: disable=unused-argument
    def get_rolebindings_side_effect(project_name, role):
        if role == "view":
            return {"role": "view", "subjects": [{"kind": "User", "name": "viewer"}]}
        raise kexc.NotFoundError(mock.Mock())

    moc.get_rolebindings = mock.Mock(side_effect=get_rolebindings_side_effect)

    users = moc.get_users_in_project("project1")

    assert users == ["viewer"]


def test_get_users_in_project_with_multiple_rolebindings(moc):
    dummy_project = {"name": "project1"}
    moc.get_project = mock.Mock(return_value=dummy_project)

    # pylint: disable=unused-argument
    def get_rolebindings_side_effect(project_name, role):
        if role in ["admin", "view", "edit"]:
            return {
                "role": role,
                "subjects": [{"kind": "User", "name": f"{role}-user"}],
            }
        raise ValueError(role)

    moc.get_rolebindings = mock.Mock(side_effect=get_rolebindings_side_effect)

    users = moc.get_users_in_project("project1")

    assert set(users) == set(["view-user", "admin-user", "edit-user"])
