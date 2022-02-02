#
# Installs Devstack with the OIDC plugin
#
set -xe

sudo apt-get update && sudo apt-get upgrade -y

sudo mkdir -p /opt/stack
sudo chown "$USER:$USER" /opt/stack

git clone https://github.com/knikolla/devstack-plugin-oidc /opt/stack/devstack-plugin-oidc
source /opt/stack/devstack-plugin-oidc/tools/config.sh

# Start Keycloak
cd /opt/stack/devstack-plugin-oidc/tools && sudo docker-compose up -d

# Install and start Devstack
git clone https://opendev.org/openstack/devstack.git /opt/stack/devstack
cd /opt/stack/devstack

cp samples/local.conf .

# Github Actions sets the CI environment variable
if [[ "${CI}" == "true" ]]; then
    sudo systemctl start mysql

    echo "
        disable_service horizon
        disable_service tempest
        INSTALL_DATABASE_SERVER_PACKAGES=False
        DATABASE_PASSWORD=root
    " >> local.conf
fi

echo "
    IP_VERSION=4
    KEYSTONE_ADMIN_ENDPOINT=True
    enable_plugin devstack-plugin-oidc https://github.com/knikolla/devstack-plugin-oidc main
" >> local.conf
./stack.sh

python3 /opt/stack/devstack-plugin-oidc/tools/test_login.py
