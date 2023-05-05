#!/bin/bash
set -x

sudo snap install microstack --edge --devmode
sudo microstack init --auto --control
microstack.openstack domain create sso
microstack.openstack identity provider create sso --domain sso
microstack.openstack mapping create sso_mapping --rules ci/mapping.json
microstack.openstack federation protocol create openid --identity-provider sso --mapping sso_mapping
microstack.openstack role create swiftoperator
microstack.openstack role create ResellerAdmin
microstack.openstack implied role create admin --implied-role swiftoperator
microstack.openstack implied role create admin --implied-role ResellerAdmin
microstack.openstack implied role create member --implied-role swiftoperator
microstack.openstack user create ceph --password ceph
microstack.openstack role add --user ceph --project admin admin
microstack.openstack service create --name swift object-store
microstack.openstack service create --name ec2-compat ec2
microstack.openstack endpoint create ec2-compat public http://localhost/notimplemented
microstack.openstack endpoint create swift public "http://$(hostname -I | awk '{print $1}')/swift/v1/AUTH_%(tenant_id)s"
