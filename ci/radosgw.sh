#!/bin/bash

set -ex

OSD_BIN_DIR=/tmp


function install_pkgs() {
  apt-get update
  apt-get install -y cephadm lvm2 ipcalc jq iproute2
}

function init_ceph() {
  DEFAULT_DEVICE=$(ip -j route show default | jq -r '.[0].dev')
  IP=$(ip -j add show dev $DEFAULT_DEVICE | jq -r '.[0].addr_info[0].local')
  PREFIX=$(ip -j add show dev $DEFAULT_DEVICE | jq -r '.[0].addr_info[0].prefixlen')
  NETWORK=$(ipcalc $IP/$PREFIX | grep -i network: | awk '{ print $2 }')

cat << EOF >/tmp/ceph.conf
[global]
rgw keystone url = https://$IP:5000
rgw keystone api version = 3
rgw keystone admin user = ceph
rgw keystone admin password = ceph
rgw keystone admin project = admin
rgw keystone admin domain = Default
rgw keystone accepted roles = member, Member, admin
rgw keystone accepted admin roles = ResellerAdmin, swiftoperator
rgw keystone token cache size = 1000
rgw keystone revocation interval = 0
rgw keystone verify ssl = false
rgw swift account in url = true
rgw s3 auth use keystone = true
rgw print continue = true
rgw frontends = beast endpoint=0.0.0.0:80
rgw keystone implicit tenants = true
rgw swift versioning enabled = true
rgw trust forwarded https = true
EOF

  cephadm bootstrap \
    --config /tmp/ceph.conf \
    --cluster-network $NETWORK \
    --mon-ip $IP \
    --dashboard-password-noupdate \
    --initial-dashboard-user admin \
    --initial-dashboard-password ceph \
    --allow-fqdn-hostname \
    --single-host-defaults
}

function osd_setup() {
  OSD1_BIN=$OSD_BIN_DIR/osd0.bin
  OSD2_BIN=$OSD_BIN_DIR/osd1.bin
  dd if=/dev/zero of=$OSD1_BIN bs=512M count=1
  dd if=/dev/zero of=$OSD2_BIN bs=512M count=1
  OSD1_DEV=$(losetup -f)
  losetup $OSD1_DEV $OSD1_BIN
  OSD2_DEV=$(losetup -f)
  losetup $OSD2_DEV $OSD2_BIN
  pvcreate $OSD1_DEV
  pvcreate $OSD2_DEV
  vgcreate rgw $OSD1_DEV $OSD2_DEV
  lvcreate -n rgw-ceph-osd0 -L 500M rgw
  lvcreate -n rgw-ceph-osd1 -L 500M rgw
  cephadm shell ceph orch daemon add osd $HOSTNAME:/dev/rgw/rgw-ceph-osd0
  cephadm shell ceph orch daemon add osd $HOSTNAME:/dev/rgw/rgw-ceph-osd1
}

function rgw_setup() {
  cephadm shell ceph orch apply rgw test --placement=1
}

install_pkgs
init_ceph
osd_setup
rgw_setup
