import requests
import json
import math
import concurrent.futures
import logging

from base64 import b64encode
from nacl import encoding, public

logging.basicConfig(level=logging.INFO)

class Github:

    def __init__(self, old_org, new_org, pat):
        self.old_org = old_org
        self.new_org = new_org
        self.token = pat

    def list_repositories(self, *, org_from):
        if org_from not in ['old', 'new']:
            print('org_from must be \'old\' or \'new\'')
            exit(1)

        org_map = {
            'new': self.new_org,
            'old': self.old_org
        }

        url = f'https://api.github.com/search/repositories?q=org:{org_map[org_from]}'
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {self.token}"
        }

        org_info = self._http_requests(url, method='get', headers=headers)
        total_page = math.ceil(org_info['total_count'] / 100)

        repositories = []
        for page in range(1, total_page + 1):
            url = f'https://api.github.com/orgs/{org_map[org_from]}/repos?simple=yes&per_page=100&page={page}'
            repositories += self._http_requests(url, method='get', headers=headers)

        return repositories

    def list_org_secrets(self):
        url = f"https://api.github.com/orgs/{self.old_org}/actions/secrets"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.token}"
        }

        res = self._http_requests(url, method='get', headers=headers)

        secrets = []
        for secret_info in res['secrets']:
            secrets.append(secret_info['name'])

        return secrets

    def list_repo_secret(self, repositories):
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.token}"
        }

        pool = concurrent.futures.ProcessPoolExecutor(max_workers=5)

        procs = []
        for repo in repositories:
            url = f"https://api.github.com/repos/{self.old_org}/{repo}/actions/secrets"
            procs.append(pool.submit(self._http_requests, url, label=repo, method='get', headers=headers))

        secret_by_repo = {}
        for p in concurrent.futures.as_completed(procs):
            label, res = p.result()

            secrets = []
            for secret_info in res['secrets']:
                secrets.append(secret_info['name'])

            if not secrets:
                continue

            secret_by_repo[label] = secrets

        return secret_by_repo

    def create_organization_secret(self, secret_name, secret_value):
        p_key = self.get_organization_public_key()
        encrypted_value = self._encrypt(p_key['key'], secret_value)

        url = f'https://api.github.com/orgs/{self.new_org}/actions/secrets/{secret_name}'

        payload = {
            'encrypted_value': encrypted_value,
            'key_id': p_key['key_id'],
            'visibility': 'all'
        }

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.token}"
        }

        res = self._http_requests(url, method='put', headers=headers, payload=payload)
        logging.info(f'{secret_name} : {res}')

    def create_repo_secret(self, list_secret_by_repo, secret_database):
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.token}"
        }
        pool = concurrent.futures.ProcessPoolExecutor(max_workers=5)

        procs = []
        for repo_name in list_secret_by_repo.keys():
            for secret_name in list_secret_by_repo[repo_name]:
                secret_value = secret_database.get(secret_name, None)
                if not secret_value:
                    continue

                p_key = self.get_repository_public_key(repo_name)
                encrypted_value = self._encrypt(p_key['key'], secret_value)
                payload = {
                    'encrypted_value': encrypted_value,
                    'key_id': p_key['key_id']
                }
                url = f'https://api.github.com/repos/{self.new_org}/{repo_name}/actions/secrets/{secret_name}'

                procs.append(pool.submit(self._http_requests, url, method='put', headers=headers, payload=payload))

        for p in concurrent.futures.as_completed(procs):
            logging.info(p.result())

    def get_organization_public_key(self):
        url = f'https://api.github.com/orgs/{self.new_org}/actions/secrets/public-key'
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.token}"
        }

        return self._http_requests(url, method='get', headers=headers)

    def get_repository_public_key(self, repo_name):
        url = f'https://api.github.com/repos/{self.new_org}/{repo_name}/actions/secrets/public-key'
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"token {self.token}"
        }

        return self._http_requests(url, method='get', headers=headers)

    @staticmethod
    def _encrypt(public_key, secret_value):
        """Encrypt a Unicode string using the public key."""
        public_key = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder())
        sealed_box = public.SealedBox(public_key)
        encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
        return b64encode(encrypted).decode("utf-8")

    @staticmethod
    def _http_requests(url, label=None, *, method, payload=None, headers=None):
        if method == ['post', 'put'] and payload is None:
            raise Exception('post method requires a payload')

        if method in ['get', 'delete'] and headers is None:
            raise Exception(f'{method} method requires a headers')

        try:
            if method == "get":
                response = requests.get(url, headers=headers)
                if response.status_code != 200:
                    raise Exception(f'Not Succeed error : {response.content}')
                if label:
                    return label, response.json()
                return response.json()
            elif method == "put":
                response = requests.put(url, headers=headers, data=json.dumps(payload))
                if response.status_code not in [201, 204]:
                    raise Exception(f'Not Succeed error : {response.content}')
                return response
            elif method == "delete":
                response = requests.delete(url, headers=headers)
                if response.status_code != 204:
                    raise Exception(f'Not Succeed error : {response.content}')
                return response
        except requests.exceptions.ConnectionError as e:
            raise Exception(f'Connection Error {e.response}')
        except requests.exceptions.HTTPError as e:
            raise Exception(f'HTTP Error {e.response}')
        except json.JSONDecodeError as e:
            raise Exception(f'Json Decode Error {e}')
