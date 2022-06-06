set -xe

# If running on Github actions, don't create a virtualenv
if [[ ! "${CI}" == "true" ]]; then
    virtualenv -p python3 /tmp/coldfront_venv
    source /tmp/coldfront_venv/bin/activate
fi

pip3 install -r test-requirements.txt
pip3 install -e .
