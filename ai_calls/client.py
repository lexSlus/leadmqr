
import requests
from django.conf import settings


class VocalyClient:
    def __init__(self):
        self.api_key = f'{settings.API_KEY}'
        self.base_url = "https://api.vocalyai.com/api/v1/"


    def do_request(self, endpoint, method='POST', payload=None, headers=None):
        headers = headers or {}
        # encoded_key = base64.b64encode(self.api_key.encode()).decode()
        headers.update({
            "X-API-KEY": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

        url = f"{self.base_url}{endpoint}"
        response = None
        if method == 'POST':
            response = requests.post(url, json=payload, headers=headers)
        elif method == 'GET':
            response = requests.get(url, headers=headers)
        return response.json()


    # def create_call(self, agent_id: str, from_number: str, to_number: str, variables: dict = None, call_settings: dict = None):
    #     endpoint = f"agent/{agent_id}/call"
    #     payload = {
    #         "fromPhoneNumber": from_number,
    #         "toPhoneNumber": to_number,
    #         "variables": variables or {},
    #         "settings": call_settings or {}
    #     }
    #     return self.do_request(endpoint, method="POST", payload=payload)

    def create_call(self, agent_id: str, from_number: str, to_number: str, variables: dict = None, call_settings: dict = None):
        endpoint = f"agent/1f385dfd-d4d6-4453-a048-dcca68dbfb92/call"
        payload = {
            "fromPhoneNumber": '+12678553731',
            # "toPhoneNumber": '+17867779396',
            "toPhoneNumber": '+17867779345',
            "settings": {
                "audioSettings": {
                    "VoiceID": "TcFVFGKruwp5AI74cZL1"
                }
            },
            "source": "app_test",
            "variables": {
                "name": "Volodymyr"
            }
        }
        response = self.do_request(endpoint, method="POST", payload=payload)
        return response