from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

DOMAIN = "dineoncampus"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up DineOnCampus from a config entry."""
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "button"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor", "button"])
    return unload_ok
