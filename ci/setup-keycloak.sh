#!/bin/bash

set -xe

sudo docker run -d --name keycloak \
    -e KEYCLOAK_ADMIN=admin \
    -e KEYCLOAK_ADMIN_PASSWORD=nomoresecret \
    -p 8080:8080 \
    -p 8443:8443 \
    quay.io/keycloak/keycloak:25.0 start-dev
