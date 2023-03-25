#!/bin/sh

set -xe

curl -sf "https://mirror.openshift.com/pub/openshift-v4/$(uname -m)/clients/ocp/stable/openshift-client-linux.tar.gz" |
	sudo tar -xzf - -C /usr/local/bin oc kubectl
