#
# Installs Devstack with the OIDC plugin
#
set -xe

sudo apt-get update
# sudo apt-get upgrade -y

sudo mkdir -p /opt/stack
sudo chown "$USER:$USER" /opt/stack

# Install CA into keycloak container and host
mkdir /opt/stack/data
cd /opt/stack/data
openssl req -x509 -nodes -newkey rsa:2048 -keyout key.pem -out cert.pem -sha256 -subj "/CN=$(hostname -I | awk '{print $1}')"
cat cert.pem key.pem > devstack-cert.pem
sudo cp devstack-cert.pem /usr/local/share/ca-certificates/devstack-cert.crt
sudo update-ca-certificates

# Install and start Devstack
git clone https://github.com/openstack/devstack.git /opt/stack/devstack
cd /opt/stack/devstack
git checkout "stable/2023.1"

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
    enable_plugin keystone https://github.com/openstack/keystone
    enable_service keystone-oidc-federation

    SWIFT_DEFAULT_BIND_PORT=8085
    SWIFT_DEFAULT_BIND_PORT_INT=8086
" >> local.conf
./stack.sh  

source /opt/stack/devstack/openrc admin admin

# Create role implication to allow admin to admin on Swift
openstack implied role create admin --implied-role ResellerAdmin

# Create oidc protocol and mappings to register keycloak identity provider
echo '
[
    {
        "local": [
            {
                "user": {
                    "name": "{0}"
                },
                "group": {
                    "name": "sso_users",
                    "domain": {
                        "name": "sso"
                    }
                }
            }
        ],
        "remote": [
            {
                "type": "OIDC-preferred_username"
            }
        ]
    }
]
' >> mapping.json

openstack mapping create --rules mapping.json sso_oidc_mapping
openstack federation protocol create --identity-provider sso --mapping sso_oidc_mapping openid
