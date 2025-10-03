set -xe

sudo docker run -d --name keycloak \
    -e KC_BOOTSTRAP_ADMIN_USERNAME=admin \
    -e KC_BOOTSTRAP_ADMIN_PASSWORD=nomoresecret \
    -e KC_BOOTSTRAP_ADMIN_CLIENT_ID=admin-cli \
    -p 8080:8080 \
    -p 8443:8443 \
    quay.io/keycloak/keycloak:25.0 start-dev
