import logging
import os
import urllib.parse
import requests

from coldfront_plugin_keycloak_usersearch import keycloak as kc


logger = logging.getLogger(__name__)


class KeycloakClient(kc.KeycloakClient):

    def create_user(self, realm, username, email, first_name, last_name):
        self._admin_auth()
        data = {
            'username': username,
            'email': email,
            'firstName': first_name,
            'lastName': last_name,
            'enabled': True,
            'emailVerified': True,
            'requiredActions': []
        }
        r = self.session.post(self.construct_url(realm, 'users'), json=data)
        logger.info(f'Created user {r.text}')
        return r

    def impersonate(self, user, realm):
        self._admin_auth()
        user = self.search_username(user, realm)[0]["id"]
        logger.info(f'Impersonating user ID {user}')
        r = self.session.post(self.construct_url(realm, f'users/{user}/impersonation'))
        return r

    def impersonate_access_token(self, user, realm, client_id, client_secret):
        user_session = requests.session()
        user_session.cookies.update(self.impersonate(user, realm).cookies)
        params = {
            'response_mode': 'fragment',
            'response_type': 'token',
            'client_id': client_id,
            'client_secret': client_secret,
            # 'redirect_uri': f'{self.url}/realms/{realm}/account/',
            'redirect_uri': os.getenv('OIDC_REDIRECT_URI')
        }
        response = user_session.get(self.auth_endpoint(realm), params=params, allow_redirects=False)
        redirect = response.headers['Location']
        token = urllib.parse.parse_qs(redirect)['access_token'][0]
        logger.warning(f'access token {token}')
        return token
