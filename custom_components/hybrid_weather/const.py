"""Constants for Hybrid Weather."""

DOMAIN = "hybrid_weather"

CONF_FORECAST = "forecast_entity"        # weather entity: forecasts, and current conditions when observations fail
CONF_CONDITION = "condition_entity"      # sensor whose state is an HA weather condition (day form)
CONF_OBSERVED = "observed_entity"        # timestamp sensor: when the observation was made
CONF_MAX_AGE = "max_age"                 # minutes; older observations fall back to the forecast entity
CONF_TEMPERATURE = "temperature_entity"
CONF_HUMIDITY = "humidity_entity"
CONF_DEW_POINT = "dew_point_entity"
CONF_PRESSURE = "pressure_entity"
CONF_WIND_SPEED = "wind_speed_entity"
CONF_WIND_GUST = "wind_gust_entity"
CONF_WIND_BEARING = "wind_bearing_entity"
CONF_CLOUD = "cloud_coverage_entity"
CONF_VISIBILITY = "visibility_entity"

# observation sensor option -> attribute of the forecast entity used as fallback
NUMERIC = {
    CONF_TEMPERATURE: "temperature",
    CONF_HUMIDITY: "humidity",
    CONF_DEW_POINT: "dew_point",
    CONF_PRESSURE: "pressure",
    CONF_WIND_SPEED: "wind_speed",
    CONF_WIND_GUST: "wind_gust_speed",
    CONF_WIND_BEARING: "wind_bearing",
    CONF_CLOUD: "cloud_coverage",
    CONF_VISIBILITY: "visibility",
}
