"""Fallback for Roost's Weheat login: OAuth with the Client ID and Secret Weheat publishes for Home Assistant.

Normally Roost's login uses the app registration the Weheat integration already has (nothing to fill in); these
application credentials are only asked for when the Weheat integration has none."""
from __future__ import annotations

from homeassistant.components.application_credentials import ClientCredential
from homeassistant.core import HomeAssistant
from homeassistant.helpers.config_entry_oauth2_flow import LocalOAuth2ImplementationWithPkce

AUTHORIZE = "https://auth.weheat.nl/auth/realms/Weheat/protocol/openid-connect/auth/"
TOKEN = "https://auth.weheat.nl/auth/realms/Weheat/protocol/openid-connect/token/"


async def async_get_auth_implementation(hass: HomeAssistant, auth_domain: str,
                                        credential: ClientCredential) -> LocalOAuth2ImplementationWithPkce:
    """With PKCE, as the Weheat integration does."""
    return LocalOAuth2ImplementationWithPkce(hass, auth_domain, credential.client_id, AUTHORIZE, TOKEN, credential.client_secret)


async def async_get_description_placeholders(hass: HomeAssistant) -> dict[str, str]:
    return {"more_info_url": "https://www.home-assistant.io/integrations/weheat/"}
