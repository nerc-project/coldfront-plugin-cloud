set -xe

virtualenv -p python3 /tmp/coldfront_venv
source /tmp/coldfront_venv/bin/activate

pip3 install -r test-requirements.txt
pip3 install -e .
