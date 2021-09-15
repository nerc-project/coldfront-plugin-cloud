# Installs and starts Microstack on a Ubuntu system
# Only run once.

openstack_cmd="microstack.openstack"

sudo snap install microstack --beta --devmode
sudo microstack init --auto --control

$openstack_cmd domain create sso
$openstack_cmd identity provider create sso --domain sso
$openstack_cmd mapping create sso_mapping --rules ci/mapping.json
$openstack_cmd federation protocol create openid --identity-provider sso --mapping sso_mapping

sudo apt-get update
sudo apt-get install -y python3-pip python3-virtualenv

virtualenv -p python3 /tmp/coldfront_venv
source /tmp/coldfront_venv/bin/activate

pip3 install -r requirements.txt
pip3 install -e .
