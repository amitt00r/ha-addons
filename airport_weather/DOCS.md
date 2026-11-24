# Airport Weather

Observed current weather from an airport's METAR reports (aviationweather.gov, no API key), published to Home
Assistant over MQTT discovery. Forecast providers present their model forecast as "current" conditions; a METAR is
what was actually observed.

Needs the Mosquitto broker add-on and the MQTT integration.

## Sensors

`sensor.<prefix>_condition` (an HA weather condition, day form: `sunny` at night means clear), `_cloud_coverage`,
`_temperature`, `_dew_point`, `_humidity` (from temperature and dew point), `_pressure`, `_wind_speed`, `_wind_gust`,
`_wind_bearing`, `_visibility`, `_observed`, `_raw`.

Condition: thunderstorm, rain, drizzle, showers, snow, hail and fog come from the report's weather codes; otherwise the
cloud cover decides (SCT = partly cloudy, BKN/OVC = cloudy, FEW/clear = sunny).
