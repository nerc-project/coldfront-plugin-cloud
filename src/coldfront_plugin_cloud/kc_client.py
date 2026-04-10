import os

import requests


class KeyCloakAPIClient:
    def __init__(self):
        self.base_url = os.getenv("KEYCLOAK_BASE_URL")
        self.realm = os.getenv("KEYCLOAK_REALM")
        self.client_id = os.getenv("KEYCLOAK_CLIENT_ID")
        self.client_secret = os.getenv("KEYCLOAK_CLIENT_SECRET")

        self.token_url = (
            f"{self.base_url}/realms/{self.realm}/protocol/openid-connect/token"
        )

    @property
    def api_client(self):
        params = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        r = requests.post(self.token_url, data=params)
        r.raise_for_status()
        headers = {
            "Authorization": ("Bearer %s" % r.json()["access_token"]),
            "Content-Type": "application/json",
        }
        session = requests.session()
        session.headers.update(headers)
        return session

    def create_group(self, group_name):
        url = f"{self.base_url}/admin/realms/{self.realm}/groups"
        payload = {"name": group_name}
        response = self.api_client.post(url, json=payload)

        # If group already exists, ignore and move on
        if response.status_code not in (201, 409):
            response.raise_for_status()

    def get_group_id(self, group_name) -> str | None:
        """Return None if group not found"""
        query = f"search={group_name}&exact=true"
        url = f"{self.base_url}/admin/realms/{self.realm}/groups?{query}"
        r = self.api_client.get(url)
        r.raise_for_status()
        r_json = r.json()
        return r_json[0]["id"] if r_json else None

    def get_user_id(self, cf_username) -> str | None:
        """Return None if user not found"""
        # (Quan) Coldfront usernames map to Keycloak usernames
        # https://github.com/nerc-project/coldfront-plugin-cloud/pull/249#discussion_r2953393852
        query = f"username={cf_username}&exact=true"
        url = f"{self.base_url}/admin/realms/{self.realm}/users?{query}"
        r = self.api_client.get(url)
        r.raise_for_status()
        r_json = r.json()
        return r_json[0]["id"] if r_json else None

    def add_user_to_group(self, user_id, group_id):
        url = f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/groups/{group_id}"
        r = self.api_client.put(url)
        r.raise_for_status()

    def remove_user_from_group(self, user_id, group_id):
        url = f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/groups/{group_id}"
        r = self.api_client.delete(url)
        r.raise_for_status()

    def get_user_groups(self, user_id) -> list[str]:
        url = f"{self.base_url}/admin/realms/{self.realm}/users/{user_id}/groups"
        r = self.api_client.get(url)
        r.raise_for_status()
        return [group["name"] for group in r.json()]
