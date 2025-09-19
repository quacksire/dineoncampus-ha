import logging
from homeassistant.components.button import ButtonEntity
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import async_update_entity

_LOGGER = logging.getLogger(__name__)

DOMAIN = "dineoncampus"

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([DineOnCampusRefreshButton(hass, entry)], True)

class DineOnCampusRefreshButton(ButtonEntity):
    """Button to manually refresh the DineOnCampus menu."""

    def __init__(self, hass, entry):
        self._hass = hass
        self._entry = entry
        self._attr_name = f"{entry.title} Refresh Menu"
        self._attr_unique_id = f"{entry.entry_id}_refresh"

    async def async_press(self) -> None:
        """Handle the button press."""
        _LOGGER.debug("Force refresh button pressed for %s", self._entry.title)

        entity_reg = er.async_get(self._hass)
        for entity_id, entry_data in entity_reg.entities.items():
            if (
                entry_data.platform == DOMAIN
                and entry_data.config_entry_id == self._entry.entry_id
                and entity_id.startswith("sensor.")
            ):
                _LOGGER.debug("Triggering async_update for %s", entity_id)
                await async_update_entity(self._hass, entity_id)
