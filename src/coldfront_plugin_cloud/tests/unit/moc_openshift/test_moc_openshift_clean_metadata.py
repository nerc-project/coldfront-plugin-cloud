# pylint: disable=missing-module-docstring
import pytest

import acct_mgt.moc_openshift


@pytest.mark.parametrize(
    "data,expected",
    [
        ({}, {}),
        ({"spec": "test"}, {"spec": "test"}),
        ({"metadata": {}, "spec": "something"}, {"metadata": {}, "spec": "something"}),
        (
            {"metadata": {"resourceVersion": "1"}, "spec": "something"},
            {"metadata": {}, "spec": "something"},
        ),
        (
            {
                "metadata": {
                    "resourceVersion": "1",
                    "uid": "",
                    "creationTimestamp": "",
                    "name": "test",
                },
                "spec": "something",
            },
            {"metadata": {"name": "test"}, "spec": "something"},
        ),
    ],
)
def test_clean_openshift_metadata(data, expected):
    assert acct_mgt.moc_openshift.clean_openshift_metadata(data) == expected
