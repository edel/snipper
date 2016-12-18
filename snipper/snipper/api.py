import os
import requests

BASE_URL = 'https://api.bitbucket.org/2.0'


class BitbucketApi(object):
    base_url = BASE_URL

    def set_config(self, config):
        self.config = config

    def get(self, endpoint):
        username = self.config.get('username')
        password = self.config.get('password')

        res = requests.get(self.build_endpoint(endpoint), auth=(username, password))
        res.raise_for_status()

        return res

    def build_endpoint(self, endpoint):
        return os.path.join(self.base_url, endpoint)


class SnippetApi(BitbucketApi):
    base_url = '{}/snippets'.format(BASE_URL)

    def get_all(self):
        res = self.get(self.config.get('username'))
        return res.json()

    def make_payload(self, is_private, title, scm, **kwargs):
        payload = {}

        if is_private is not None:
            payload.update({'is_private': is_private})
        if title is not None:
            payload.update({'title': title})
        if scm is not None:
            payload.update({'scm': scm})

        return payload

    def create_snippet(self, files, is_private, title, scm):

        username = self.config.get('username')
        password = self.config.get('password')

        payload = self.make_payload(is_private, title, scm)
        response = requests.post(
            self.base_url,
            data=payload,
            files=files,
            auth=(username, password)
        )

        return response