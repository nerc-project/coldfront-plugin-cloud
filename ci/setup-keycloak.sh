#!/bin/bash

set -xe

sudo docker run -d --name keycloak \
    -e KEYCLOAK_ADMIN=admin \
    -e KEYCLOAK_ADMIN_PASSWORD=nomoresecret \
    -p 8080:8080 \
    -p 8443:8443 \
    quay.io/keycloak/keycloak:25.0 start-dev

# wait for keycloak to be ready
until curl -s http://localhost:8080/auth/realms/master; do
    echo "Waiting for Keycloak to be ready..."
    sleep 5
done

# Create client and add admin role to client's service account
ACCESS_TOKEN=$(curl -X POST "http://localhost:8080/realms/master/protocol/openid-connect/token" \
     -d "username=admin" \
     -d "password=nomoresecret" \
     -d "grant_type=password" \
     -d "client_id=admin-cli" \
     -d "scope=openid" \
| jq -r '.access_token')


curl -X POST "http://localhost:8080/admin/realms/master/clients" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '{
        "clientId": "coldfront",
        "secret": "nomoresecret",
        "redirectUris": ["http://localhost:8080/*"],
        "serviceAccountsEnabled": true
    }'

COLDFRONT_CLIENT_ID=$(curl -X GET "http://localhost:8080/admin/realms/master/clients?clientId=coldfront" \
    -H "Authorization: Bearer $ACCESS_TOKEN" | jq -r '.[0].id')


COLDFRONT_SERVICE_ACCOUNT_ID=$(curl -X GET "http://localhost:8080/admin/realms/master/clients/$COLDFRONT_CLIENT_ID/service-account-user" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
| jq -r '.id')

ADMIN_ROLE_ID=$(curl -X GET "http://localhost:8080/admin/realms/master/roles/admin" \
    -H "Authorization: Bearer $ACCESS_TOKEN" | jq -r '.id')

# Add admin role to the service account user
curl -X POST "http://localhost:8080/admin/realms/master/users/$COLDFRONT_SERVICE_ACCOUNT_ID/role-mappings/realm" \
    -H "Authorization: Bearer $ACCESS_TOKEN" \
    -H "Content-Type: application/json" \
    -d '[
            {
                "id": "'$ADMIN_ROLE_ID'",
                "name": "admin"
            }
        ]'
