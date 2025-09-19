import aiohttp
from datetime import datetime, timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.util import dt as dt_util
import logging
import re

_LOGGER = logging.getLogger(__name__)

MENU_URL = "https://apiv4.dineoncampus.com/locations/{}/menu?date={}&period={}"
PERIODS_URL = "https://apiv4.dineoncampus.com/locations/{}/periods/?date={}"
SCAN_INTERVAL = timedelta(minutes=5)

async def async_setup_entry(hass, entry, async_add_entities):
    _LOGGER.debug("Setting up DineOnCampus sensor with config: %s", entry.data)
    main = DineOnCampusMenuSensor(entry.data)
    async_add_entities([main], True)

    async def _spawn_categories():
        cats = main._attrs.get("categories", {})
        entities = [DineOnCampusCategorySensor(main, cname) for cname in cats]
        if entities:
            async_add_entities(entities, True)
            _LOGGER.debug("Spawned category sensors: %s", list(cats.keys()))

    # Delay until main has updated once
    hass.loop.call_later(5, lambda: hass.async_create_task(_spawn_categories()))

class DineOnCampusMenuSensor(SensorEntity):
    _attr_should_poll = True

    def __init__(self, config):
        self._school_id = config["school_id"]
        self._location_id = config["location_id"]
        self._location_name = config.get("location_name", "Dining Hall")
        self._period_id = config.get("period_id")
        self._period_name = config.get("period_name", "")
        self._dynamic = config.get("dynamic", False)
        self._windows = config.get("period_windows", {})

        if self._dynamic:
            self._attr_name = f"{self._location_name} (Current Menu)"
            raw_slug = f"{self._location_name}_current_menu"
            self._attr_unique_id = f"{self._school_id}_{self._location_id}_dynamic"
        else:
            self._attr_name = f"{self._location_name} {self._period_name}".strip()
            raw_slug = f"{self._location_name}_{self._period_name}"
            self._attr_unique_id = f"{self._school_id}_{self._location_id}_{self._period_id}"

        slug = re.sub(r'[^a-zA-Z0-9]+', '_', raw_slug).lower().strip("_")
        self.entity_id = f"sensor.{slug}"

        self._state = None
        self._attrs = {}
        self._last_good_attrs = {}
        self._last_good_state = None

    @property
    def extra_state_attributes(self):
        return self._attrs

    async def _fetch_json(self, url: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                text = await resp.text()
                if resp.status != 200:
                    _LOGGER.error("API %s -> HTTP %s: %s", url, resp.status, text)
                    return {}
                try:
                    return await resp.json()
                except Exception as e:
                    _LOGGER.error("JSON parse error for %s: %s", url, e)
                    return {}

    async def _resolve_period_id(self, today: str, period_name: str):
        payload = await self._fetch_json(PERIODS_URL.format(self._location_id, today))
        periods = payload.get("periods", []) if isinstance(payload, dict) else payload
        for p in periods or []:
            if p.get("name", "").lower() == period_name.lower():
                return p.get("id")
        return None

    def _match_period_by_time(self):
        now = dt_util.now().time()
        for slug, win in self._windows.items():
            try:
                st = datetime.strptime(win["start"], "%H:%M").time()
                en = datetime.strptime(win["end"], "%H:%M").time()
                if st <= now <= en:
                    return win["id"], win["name"]
            except Exception as e:
                _LOGGER.debug("Bad window for %s: %s", slug, e)
        return None, None

    async def async_update(self):
        today = dt_util.now().strftime("%Y-%m-%d")
        period_id = self._period_id
        period_name = self._period_name
        base_name = self._location_name

        if not self._dynamic and self._period_name:
            resolved_id = await self._resolve_period_id(today, self._period_name)
            if resolved_id:
                period_id = resolved_id
                _LOGGER.debug("Resolved fresh period_id=%s for %s", resolved_id, self._period_name)
            else:
                self._state = 0
                self._attrs = {"categories": {}, "period": self._period_name, "active_period": self._period_name, "windows": self._windows}
                return

        if self._dynamic:
            pid, pname = self._match_period_by_time()
            if not pid:
                self._state = 0
                self._attrs = {"categories": {}, "period": "", "active_period": None, "windows": self._windows}
                return
            period_id, period_name = pid, pname
            resolved_id = await self._resolve_period_id(today, period_name)
            if resolved_id:
                period_id = resolved_id
                _LOGGER.debug("Resolved fresh period_id=%s for %s", resolved_id, period_name)
            else:
                self._state = 0
                self._attrs = {"categories": {}, "period": period_name, "active_period": period_name, "windows": self._windows}
                return

        try:
            menu_payload = await self._fetch_json(MENU_URL.format(self._location_id, today, period_id))
            _LOGGER.debug("Menu payload for %s [%s]: %s", period_name, period_id, str(menu_payload)[:500])

            categories = {}
            total = 0
            period = menu_payload.get("period", {}) if isinstance(menu_payload, dict) else {}
            for cat in period.get("categories", []) or []:
                cname = cat.get("name", "Unknown")
                items = [it.get("name") for it in (cat.get("items", []) or [])]
                categories[cname] = items
                total += len(items)

            self._state = total
            self._attrs = {
                "categories": categories,
                "period": period_name,
                "active_period": period_name,
                "windows": self._windows,
            }

        except Exception as e:
            _LOGGER.exception("Failed to parse menu for %s: %s", period_name, e)
            self._state = 0
            self._attrs = {"categories": {}, "period": period_name or "", "active_period": period_name, "windows": self._windows}

class DineOnCampusCategorySensor(SensorEntity):
    """One sensor per menu category."""

    def __init__(self, parent, category_name):
        self._parent = parent
        self._category = category_name
        self._attr_unique_id = f"{parent._attr_unique_id}_{category_name.lower().replace(' ', '_')}"
        self._attr_name = f"{parent._location_name} - {category_name}"
        slug = re.sub(r'[^a-zA-Z0-9]+', '_', self._attr_name).lower().strip("_")
        self.entity_id = f"sensor.{slug}"
        self._state = None
        self._attrs = {}

    async def async_update(self):
        cats = self._parent._attrs.get("categories", {})
        items = cats.get(self._category, [])
        self._state = len(items)
        self._attrs = {"items": items}

    @property
    def extra_state_attributes(self):
        return self._attrs
