#
# Installs Devstack with the OIDC plugin
#
set -xe

sudo apt-get update
# sudo apt-get upgrade -y

sudo mkdir -p /opt/stack
sudo chown "$USER:$USER" /opt/stack

if [[ ! "${CI}" == "true" ]]; then
    sudo apt-get install docker.io docker-compose -y
fi

git clone https://github.com/knikolla/devstack-plugin-oidc /opt/stack/devstack-plugin-oidc
source /opt/stack/devstack-plugin-oidc/tools/config.sh

# Start Keycloak
cd /opt/stack/devstack-plugin-oidc/tools && sudo docker-compose up -d

# Install and start Devstack
git clone https://github.com/openstack/devstack.git /opt/stack/devstack
git checkout "stable/2023.1"
cd /opt/stack/devstack

cp samples/local.conf .

# Github Actions sets the CI environment variable
if [[ "${CI}" == "true" ]]; then
    sudo systemctl start mysql

    echo "
        INSTALL_DATABASE_SERVER_PACKAGES=False
        DATABASE_PASSWORD=root
    " >> local.conf
fi

echo "
    disable_service horizon
    disable_service tempest
    enable_service s-proxy s-object s-container s-account
    SWIFT_REPLICAS=1
    IP_VERSION=4
    GIT_DEPTH=1
    GIT_BASE=https://github.com
    KEYSTONE_ADMIN_ENDPOINT=True
    enable_plugin devstack-plugin-oidc https://github.com/knikolla/devstack-plugin-oidc main

    SWIFT_DEFAULT_BIND_PORT=8085
    SWIFT_DEFAULT_BIND_PORT_INT=8086
" >> local.conf
./stack.sh

python3 /opt/stack/devstack-plugin-oidc/tools/test_login.py

source /opt/stack/devstack/openrc admin admin

# Create role implication to allow admin to admin on Swift
openstack implied role create admin --implied-role ResellerAdmin
