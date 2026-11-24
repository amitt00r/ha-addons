"""Hybrid Weather entity.

Current conditions come from observation sensors (e.g. an airport METAR) while they are fresh, otherwise from the
forecast weather entity. Forecasts are always the forecast entity's, fetched on demand with weather.get_forecasts,
so nothing is copied or cached. Values are taken as metric (°C, hPa, km/h, km, mm), HA's display units here.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.weather import (
    ATTR_CONDITION_CLEAR_NIGHT, ATTR_CONDITION_SUNNY, Forecast, WeatherEntity, WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_NAME, STATE_UNAVAILABLE, STATE_UNKNOWN, UnitOfLength, UnitOfPrecipitationDepth, UnitOfPressure,
    UnitOfSpeed, UnitOfTemperature,
)
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, State, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import dt as dt_util

from .const import CONF_CONDITION, CONF_FORECAST, CONF_MAX_AGE, CONF_OBSERVED, NUMERIC

CONDITIONS = {"clear-night", "cloudy", "exceptional", "fog", "hail", "lightning", "lightning-rainy", "partlycloudy",
              "pouring", "rainy", "snowy", "snowy-rainy", "sunny", "windy", "windy-variant"}
# get_forecasts returns display-unit keys; hand them back as native ones (same units here)
NATIVE_KEYS = {"temperature": "native_temperature", "templow": "native_templow", "pressure": "native_pressure",
               "wind_speed": "native_wind_speed", "wind_gust_speed": "native_wind_gust_speed",
               "precipitation": "native_precipitation", "apparent_temperature": "native_apparent_temperature",
               "dew_point": "native_dew_point"}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([HybridWeather(entry)])


def _num(st: State | None) -> float | None:
    if st is None:
        return None
    try:
        return float(st.state)
    except (TypeError, ValueError):
        return None


class HybridWeather(WeatherEntity):
    _attr_should_poll = False
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._o = dict(entry.options)
        self._attr_name = entry.data[CONF_NAME]
        self._attr_unique_id = entry.entry_id
        self._fc = self._o[CONF_FORECAST]

    # ------------------------------------------------------------ sources
    def _st(self, key: str) -> State | None:
        eid = self._o.get(key)
        return self.hass.states.get(eid) if eid else None

    def _src(self) -> State | None:
        return self.hass.states.get(self._fc)

    def _fresh(self) -> bool:
        c = self._st(CONF_CONDITION)
        if c is None or c.state not in CONDITIONS:
            return False
        if self._o.get(CONF_OBSERVED):
            o = self._st(CONF_OBSERVED)
            t = dt_util.parse_datetime(o.state) if o and o.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE) else None
            if t is None or dt_util.utcnow() - t > timedelta(minutes=float(self._o.get(CONF_MAX_AGE, 120))):
                return False
        return True

    def _value(self, key: str) -> float | None:
        if self._fresh() and self._o.get(key):
            v = _num(self._st(key))
            if v is not None:
                return v
        src = self._src()
        return src.attributes.get(NUMERIC[key]) if src else None

    # ------------------------------------------------------------ state
    @property
    def available(self) -> bool:
        src = self._src()
        return self._fresh() or (src is not None and src.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE))

    @property
    def condition(self) -> str | None:
        if self._fresh():
            cond = self._st(CONF_CONDITION).state
            sun = self.hass.states.get("sun.sun")
            if cond == ATTR_CONDITION_SUNNY and sun is not None and sun.state == "below_horizon":
                return ATTR_CONDITION_CLEAR_NIGHT
            return cond
        src = self._src()
        return src.state if src and src.state in CONDITIONS else None

    native_temperature = property(lambda s: s._value("temperature_entity"))
    humidity = property(lambda s: s._value("humidity_entity"))
    native_dew_point = property(lambda s: s._value("dew_point_entity"))
    native_pressure = property(lambda s: s._value("pressure_entity"))
    native_wind_speed = property(lambda s: s._value("wind_speed_entity"))
    native_wind_gust_speed = property(lambda s: s._value("wind_gust_entity"))
    wind_bearing = property(lambda s: s._value("wind_bearing_entity"))
    cloud_coverage = property(lambda s: s._value("cloud_coverage_entity"))
    native_visibility = property(lambda s: s._value("visibility_entity"))

    @property
    def uv_index(self) -> float | None:   # observations have none
        src = self._src()
        return src.attributes.get("uv_index") if src else None

    @property
    def native_apparent_temperature(self) -> float | None:   # only consistent when the temperature is the source's too
        src = self._src()
        return None if self._fresh() or src is None else src.attributes.get("apparent_temperature")

    @property
    def attribution(self) -> str | None:
        src = self._src()
        fc = src.attributes.get("attribution") if src else None
        if self._fresh():
            c = self._st(CONF_CONDITION)
            obs = c.attributes.get("station") or c.attributes.get("friendly_name") or c.entity_id
            return f"Current: {obs}. Forecast: {fc or self._fc}"
        return fc

    @property
    def extra_state_attributes(self) -> dict:
        return {"current_source": "observation" if self._fresh() else "forecast_entity", "forecast_source": self._fc}

    @property
    def supported_features(self) -> WeatherEntityFeature:
        src = self._src()
        f = WeatherEntityFeature(src.attributes.get("supported_features", 0)) if src else WeatherEntityFeature(0)
        return f & (WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
                    | WeatherEntityFeature.FORECAST_TWICE_DAILY)

    # ------------------------------------------------------------ forecasts
    async def _forecast(self, kind: str) -> list[Forecast] | None:
        resp = await self.hass.services.async_call(
            "weather", "get_forecasts", {"entity_id": self._fc, "type": kind}, blocking=True, return_response=True)
        out = []
        for f in (resp or {}).get(self._fc, {}).get("forecast", []):
            out.append({NATIVE_KEYS.get(k, k): v for k, v in f.items()})
        return out

    async def async_forecast_daily(self) -> list[Forecast] | None:
        return await self._forecast("daily")

    async def async_forecast_hourly(self) -> list[Forecast] | None:
        return await self._forecast("hourly")

    async def async_forecast_twice_daily(self) -> list[Forecast] | None:
        return await self._forecast("twice_daily")

    # ------------------------------------------------------------ updates
    async def async_added_to_hass(self) -> None:
        watched = {self._fc, "sun.sun"} | {v for k, v in self._o.items() if k.endswith("_entity") and v}

        @callback
        def _changed(event: Event[EventStateChangedData]) -> None:
            self.async_write_ha_state()
            if event.data["entity_id"] == self._fc:   # the source refreshed: forecast subscribers re-fetch
                self.hass.async_create_task(self.async_update_listeners(None))

        self.async_on_remove(async_track_state_change_event(self.hass, list(watched), _changed))
