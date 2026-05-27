#!/bin/bash

set -xe

# If running on Github actions, don't create a virtualenv
# Else install postgres
if [[ ! "${CI}" == "true" ]]; then
    virtualenv -p python3 /tmp/coldfront_venv
    source /tmp/coldfront_venv/bin/activate
else
    sudo systemctl start postgresql.service
    sudo -u postgres psql -c "ALTER USER postgres PASSWORD 'postgres';"
fi

python -m pip install --upgrade pip
pip3 install -r test-requirements.txt
pip3 install -e .
