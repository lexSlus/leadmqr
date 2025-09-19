
import requests
from django.conf import settings


import logging
logger = logging.getLogger('playwright_bot')

class VocalyClient:
    def __init__(self):
        self.api_key = f'{settings.API_KEY}'
        self.base_url = "https://api.vocalyai.com/api/v1/"


    def do_request(self, endpoint, method='POST', payload=None, headers=None):
        headers = headers or {}
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
        try:
            if response.text.strip():
                return response.json()
            else:
                # Пустой ответ - возможно успешный запрос без данных
                logger.info("Received empty response, treating as success")
                return {"status": "success", "message": "Empty response"}
        except Exception as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Response text: {response.text}")
            raise


    def create_call(self, agent_id: str, from_number: str, to_number: str, variables: dict = None):
        endpoint = f"agent/{agent_id}/call"
        payload = {
            "fromPhoneNumber": from_number,
            # "toPhoneNumber": '+17867779396',
            "toPhoneNumber": to_number,
            "settings": {
                "audioSettings": {
                    "voiceID": "TcFVFGKruwp5AI74cZL1"
                }
            },
            "source": "app_test",
            "variables": variables,
        }

        response = self.do_request(endpoint, method="POST", payload=payload)
        logger.info(f'call{response}')
        return response