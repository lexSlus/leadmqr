# jobber_integration.py

import requests
import logging
from typing import Dict, Any, Tuple, Optional

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class JobberClient:
    """
    Jobber API client for managing leads and clients.
    """
    
    # Constants
    ACCESS_TOKEN_KEY = "jobber_access_token"
    REFRESH_TOKEN_KEY = "jobber_refresh_token"
    API_URL = "https://api.getjobber.com/api/graphql"
    API_VERSION = "2025-04-16"
    
    def __init__(self):
        self.client_id = settings.JOBBER_CLIENT_ID
        self.client_secret = settings.JOBBER_CLIENT_SECRET
        self.token_url = settings.JOBBER_TOKEN_URL
    
    def refresh_access_token(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Refreshes the access token using the refresh token and saves the new tokens to the cache.
        This supports refresh token rotation.
        """
        refresh_token = cache.get(self.REFRESH_TOKEN_KEY)
        if not refresh_token:
            logger.error("Jobber: Refresh token not found. Please re-authenticate manually.")
            return None, None

        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }

        try:
            response = requests.post(self.token_url, data=payload)
            response.raise_for_status()
            data = response.json()

            access_token = data["access_token"]
            new_refresh_token = data.get("refresh_token", refresh_token)
            expires_in = data.get("expires_in", 7200)

            # Save the new tokens to the cache
            cache.set(self.ACCESS_TOKEN_KEY, access_token, timeout=expires_in - 300)
            cache.set(self.REFRESH_TOKEN_KEY, new_refresh_token, timeout=None)

            logger.info("Jobber: Successfully refreshed access token.")
            return access_token, new_refresh_token
        except requests.exceptions.RequestException as e:
            logger.error("Jobber: Failed to refresh access token. Error: %s", e)
            return None, None

    def get_access_token(self) -> Optional[str]:
        """
        Gets the access token from the cache or refreshes it if it's missing/expired.
        """
        access_token = cache.get(self.ACCESS_TOKEN_KEY)
        if access_token:
            return access_token
        
        logger.warning("Jobber: Access token not found or expired. Refreshing...")
        access_token, _ = self.refresh_access_token()
        return access_token

    def split_name(self, full_name: str) -> Tuple[str, str]:
        """A simple utility to split a full name into first and last names."""
        parts = full_name.strip().split()
        if not parts:
            return "", ""
        if len(parts) > 1:
            return parts[0], " ".join(parts[1:])
        return parts[0], ""

    def create_lead(self, lead_variables: Dict[str, Any], phone: str) -> bool:
        """
        Creates a new lead in Jobber.
        
        Args:
            lead_variables: Dictionary containing lead data
            phone: Phone number of the lead
            
        Returns:
            bool: True if lead was created successfully, False otherwise
        """
        access_token = self.get_access_token()
        if not access_token:
            logger.error("Jobber: Could not get access token. Aborting lead submission.")
            return False

        first_name, last_name = self.split_name(lead_variables.get("name", "Unknown Lead"))

        graphql_query = """
            mutation CreateLead($input: ClientCreateInput!) {
              clientCreate(input: $input) {
                client { id, isLead }
                userErrors { message, path }
              }
            }
        """
        
        variables = {
            "input": {
                "firstName": first_name,
                "lastName": last_name,
                "phones": [{"number": phone}],
                "emails": []
            }
        }
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": self.API_VERSION,
        }
        
        payload = {"query": graphql_query, "variables": variables}

        try:
            response = requests.post(self.API_URL, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            logger.info("Jobber: Response: %s", result)
            
            # Handle response
            if result.get("errors"):
                logger.error("Jobber: GraphQL error on lead creation: %s", result["errors"])
                return False
            elif result.get("data") and result["data"]["clientCreate"]["client"]:
                client_id = result["data"]["clientCreate"]["client"]["id"]
                logger.info("Jobber: Successfully created lead with ID %s", client_id)
                return True
            else:
                logger.info("Jobber: Lead creation completed (check logs for details)")
                return True

        except requests.exceptions.RequestException as e:
            if e.response and e.response.status_code == 401:
                logger.warning("Jobber: Access token is invalid or expired. It will be refreshed on the next run.")
            else:
                logger.error("Jobber: Failed to send lead. HTTP Error: %s", e)
            return False

    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves client information from Jobber.
        
        Args:
            client_id: Jobber client ID
            
        Returns:
            Dict containing client info or None if failed
        """
        access_token = self.get_access_token()
        if not access_token:
            logger.error("Jobber: Could not get access token for client info.")
            return None

        graphql_query = """
            query GetClient($id: ID!) {
              client(id: $id) {
                id
                firstName
                lastName
                phones { number }
                emails { address }
                isLead
              }
            }
        """
        
        variables = {"id": client_id}
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "X-JOBBER-GRAPHQL-VERSION": self.API_VERSION,
        }
        
        payload = {"query": graphql_query, "variables": variables}

        try:
            response = requests.post(self.API_URL, json=payload, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            if result.get("errors"):
                logger.error("Jobber: GraphQL error getting client info: %s", result["errors"])
                return None
            
            return result.get("data", {}).get("client")

        except requests.exceptions.RequestException as e:
            logger.error("Jobber: Failed to get client info. Error: %s", e)
            return None


# Global instance for backward compatibility
_jobber_client = JobberClient()


def send_lead_to_jobber(lead_variables: Dict[str, Any], phone: str):
    """
    Backward compatibility function.
    """
    return _jobber_client.create_lead(lead_variables, phone)
