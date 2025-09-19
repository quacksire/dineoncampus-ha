import aiohttp
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from datetime import date
from homeassistant import config_entries
import logging
from . import DOMAIN

_LOGGER = logging.getLogger(__name__)

SCHOOLS_URL = "https://apiv4.dineoncampus.com/sites/public"
LOCATIONS_URL = "https://apiv4.dineoncampus.com/locations/status_by_site?siteId={}"
PERIODS_URL = "https://apiv4.dineoncampus.com/locations/{}/periods/?date={}"

DEFAULT_WINDOWS = {
    "breakfast": ("05:00", "10:30"),
    "lunch": ("11:00", "15:00"),
    "dinner": ("16:00", "23:00"),
    "everyday": ("00:00", "23:59"),
}

class DineOnCampusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        _LOGGER.debug("Step user called with input=%s", user_input)
        try:
            if user_input is None:
                async with aiohttp.ClientSession() as session:
                    async with session.get(SCHOOLS_URL) as resp:
                        text = await resp.text()
                        _LOGGER.debug("Schools response [%s]: %s", resp.status, text[:500])
                        data = await resp.json()
                        self.schools = {s["name"]: s["id"] for s in (data if isinstance(data, list) else data.get("sites", []))}
                return self.async_show_form(
                    step_id="user",
                    data_schema=vol.Schema({vol.Required("school"): vol.In(list(self.schools.keys()))}),
                )
            self.school_name = user_input["school"]
            self.school_id = self.schools[self.school_name]
            return await self.async_step_location()
        except Exception as e:
            _LOGGER.exception("Error in async_step_user: %s", e)
            return self.async_show_form(step_id="user", errors={"base": "unknown"})

    async def async_step_location(self, user_input=None):
        _LOGGER.debug("Step location called with input=%s", user_input)
        try:
            if user_input is None:
                async with aiohttp.ClientSession() as session:
                    async with session.get(LOCATIONS_URL.format(self.school_id)) as resp:
                        text = await resp.text()
                        _LOGGER.debug("Locations response [%s]: %s", resp.status, text[:500])
                        data = await resp.json()
                        self.locations = {l["name"]: l["id"] for l in (data.get("locations", []) if isinstance(data, dict) else data)}
                return self.async_show_form(
                    step_id="location",
                    data_schema=vol.Schema({vol.Required("location"): vol.In(list(self.locations.keys()))}),
                )
            self.location_name = user_input["location"]
            self.location_id = self.locations[self.location_name]
            return await self.async_step_dynamic_or_static()
        except Exception as e:
            _LOGGER.exception("Error in async_step_location: %s", e)
            return self.async_show_form(step_id="location", errors={"base": "unknown"})

    async def async_step_dynamic_or_static(self, user_input=None):
        _LOGGER.debug("Step dynamic_or_static called with input=%s", user_input)
        try:
            if user_input is None:
                return self.async_show_form(
                    step_id="dynamic_or_static",
                    data_schema=vol.Schema({vol.Required("mode", default="dynamic"): vol.In(["dynamic", "static"])}),
                )
            self.mode = user_input["mode"]
            if self.mode == "static":
                return await self.async_step_period()
            else:
                return await self.async_step_dynamic_windows()
        except Exception as e:
            _LOGGER.exception("Error in async_step_dynamic_or_static: %s", e)
            return self.async_show_form(step_id="dynamic_or_static", errors={"base": "unknown"})

    async def async_step_dynamic_windows(self, user_input=None):
        _LOGGER.debug("Step dynamic_windows called with input=%s", user_input)
        today = date.today().strftime("%Y-%m-%d")
        try:
            if user_input is None:
                async with aiohttp.ClientSession() as session:
                    async with session.get(PERIODS_URL.format(self.location_id, today)) as resp:
                        text = await resp.text()
                        _LOGGER.debug("Periods response [%s]: %s", resp.status, text[:500])
                        data = await resp.json()
                        self.periods = (data.get("periods", []) if isinstance(data, dict) else data) or []

                schema_dict = {}
                for p in self.periods:
                    slug = p.get("slug", p.get("name", "period")).lower()
                    default_start, default_end = ("00:00", "23:59")
                    for key, (dstart, dend) in DEFAULT_WINDOWS.items():
                        if key in slug:
                            default_start, default_end = dstart, dend
                            break
                    schema_dict[vol.Required(f"{slug}_start", default=default_start)] = cv.string
                    schema_dict[vol.Required(f"{slug}_end", default=default_end)] = cv.string

                return self.async_show_form(
                    step_id="dynamic_windows",
                    data_schema=vol.Schema(schema_dict),
                )

            # validation
            errors = {}
            valid = False
            for p in self.periods:
                slug = p.get("slug", p.get("name", "period")).lower()
                st = user_input[f"{slug}_start"]
                en = user_input[f"{slug}_end"]
                _LOGGER.debug("Validating window %s: %s-%s", slug, st, en)
                if st < en:
                    valid = True
            if not valid:
                errors["base"] = "invalid_time_window"
                schema_dict = {}
                for p in self.periods:
                    slug = p.get("slug", p.get("name", "period")).lower()
                    schema_dict[vol.Required(f"{slug}_start", default=user_input[f"{slug}_start"])] = cv.string
                    schema_dict[vol.Required(f"{slug}_end", default=user_input[f"{slug}_end"])] = cv.string
                return self.async_show_form(
                    step_id="dynamic_windows",
                    data_schema=vol.Schema(schema_dict),
                    errors=errors,
                )

            windows = {}
            for p in self.periods:
                slug = p.get("slug", p.get("name", "period")).lower()
                windows[slug] = {
                    "id": p.get("id"),
                    "name": p.get("name"),
                    "start": user_input[f"{slug}_start"],
                    "end": user_input[f"{slug}_end"],
                }
            _LOGGER.debug("Final dynamic windows config: %s", windows)

            await self.async_set_unique_id(f"{self.school_id}_{self.location_id}_dynamic")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{self.school_name} - {self.location_name} (Dynamic)",
                data={
                    "school_id": self.school_id,
                    "location_id": self.location_id,
                    "location_name": self.location_name,
                    "dynamic": True,
                    "period_windows": windows
                }
            )
        except Exception as e:
            _LOGGER.exception("Error in async_step_dynamic_windows: %s", e)
            return self.async_show_form(step_id="dynamic_windows", errors={"base": "unknown"})

    async def async_step_period(self, user_input=None):
        _LOGGER.debug("Step period called with input=%s", user_input)
        today = date.today().strftime("%Y-%m-%d")
        try:
            if user_input is None:
                async with aiohttp.ClientSession() as session:
                    async with session.get(PERIODS_URL.format(self.location_id, today)) as resp:
                        text = await resp.text()
                        _LOGGER.debug("Periods response [%s]: %s", resp.status, text[:500])
                        data = await resp.json()
                        self.periods = {p["name"]: p["id"] for p in (data.get("periods", []) if isinstance(data, dict) else data)}
                return self.async_show_form(
                    step_id="period",
                    data_schema=vol.Schema({vol.Required("period"): vol.In(list(self.periods.keys()))}),
                )
            self.period_name = user_input["period"]
            self.period_id = self.periods[self.period_name]
            await self.async_set_unique_id(f"{self.school_id}_{self.location_id}_{self.period_id}")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"{self.school_name} - {self.location_name} - {self.period_name}",
                data={
                    "school_id": self.school_id,
                    "location_id": self.location_id,
                    "location_name": self.location_name,
                    "period_id": self.period_id,
                    "period_name": self.period_name,
                    "dynamic": False
                }
            )
        except Exception as e:
            _LOGGER.exception("Error in async_step_period: %s", e)
            return self.async_show_form(step_id="period", errors={"base": "unknown"})

    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfigure initiated from UI."""
        _LOGGER.debug("Reconfigure called with input=%s", user_input)
        entry = self._get_reconfigure_entry()
        current = entry.data

        if user_input is None:
            if current.get("dynamic"):
                schema_dict = {}
                for slug, win in current.get("period_windows", {}).items():
                    schema_dict[vol.Required(f"{slug}_start", default=win["start"])] = cv.string
                    schema_dict[vol.Required(f"{slug}_end", default=win["end"])] = cv.string
                return self.async_show_form(step_id="reconfigure", data_schema=vol.Schema(schema_dict))
            else:
                return self.async_show_form(
                    step_id="reconfigure",
                    data_schema=vol.Schema({
                        vol.Required("period", default=current.get("period_name")): vol.In([current.get("period_name")])
                    }),
                )

        if current.get("dynamic"):
            new_windows = {}
            for slug in current.get("period_windows", {}):
                new_windows[slug] = {
                    **current["period_windows"][slug],
                    "start": user_input[f"{slug}_start"],
                    "end": user_input[f"{slug}_end"],
                }
            data = {**current, "period_windows": new_windows}
        else:
            data = {
                **current,
                "period_name": user_input["period"],
                "period_id": current.get("period_id"),
            }

        _LOGGER.debug("Reconfigure saving new data=%s", data)
        self.hass.config_entries.async_update_entry(entry, data=data)
        return self.async_abort(reason="reconfigure_success")
