"""Config and options flow for Hybrid Weather."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_CLOUD, CONF_CONDITION, CONF_DEW_POINT, CONF_FORECAST, CONF_HUMIDITY, CONF_MAX_AGE, CONF_OBSERVED,
    CONF_PRESSURE, CONF_TEMPERATURE, CONF_VISIBILITY, CONF_WIND_BEARING, CONF_WIND_GUST, CONF_WIND_SPEED, DOMAIN,
)

SENSOR = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
OPTIONAL_SENSORS = [CONF_TEMPERATURE, CONF_HUMIDITY, CONF_DEW_POINT, CONF_PRESSURE, CONF_WIND_SPEED, CONF_WIND_GUST,
                    CONF_WIND_BEARING, CONF_CLOUD, CONF_VISIBILITY]


def _schema(d: dict[str, Any], with_name: bool) -> vol.Schema:
    s: dict = {}
    if with_name:
        s[vol.Required(CONF_NAME, default=d.get(CONF_NAME, "Hybrid Weather"))] = str
    s[vol.Required(CONF_FORECAST, default=d.get(CONF_FORECAST, vol.UNDEFINED))] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="weather"))
    s[vol.Required(CONF_CONDITION, default=d.get(CONF_CONDITION, vol.UNDEFINED))] = SENSOR
    s[vol.Optional(CONF_OBSERVED, description={"suggested_value": d.get(CONF_OBSERVED)})] = SENSOR
    s[vol.Required(CONF_MAX_AGE, default=d.get(CONF_MAX_AGE, 120))] = selector.NumberSelector(
        selector.NumberSelectorConfig(min=5, max=1440, step=5, unit_of_measurement="min",
                                      mode=selector.NumberSelectorMode.BOX))
    for k in OPTIONAL_SENSORS:
        s[vol.Optional(k, description={"suggested_value": d.get(k)})] = SENSOR
    return vol.Schema(s)


class HybridWeatherConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            name = user_input.pop(CONF_NAME)
            return self.async_create_entry(title=name, data={CONF_NAME: name}, options=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema({}, True))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return HybridWeatherOptionsFlow()


class HybridWeatherOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_schema(dict(self.config_entry.options), False))
