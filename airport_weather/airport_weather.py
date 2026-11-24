"""Airport Weather add-on.

Polls aviationweather.gov for one station's METAR (observed weather, issued every 30 min plus SPECIs) and
publishes it as MQTT-discovered sensors: an HA weather condition, cloud coverage, temperature, dew point,
humidity, pressure, wind, visibility, observation time and the raw report.
"""
import json
import math
import os
import time
import urllib.request

import paho.mqtt.client as mqtt

OPTS = json.load(open("/data/options.json"))
STATION = OPTS["station"].upper()
PREFIX = OPTS["entity_prefix"]
POLL = OPTS["poll_minutes"] * 60
TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")

BASE = f"airport_weather/{STATION.lower()}"
AVAIL = f"{BASE}/availability"
STATE = f"{BASE}/state"
UID = f"airport_weather_{STATION.lower()}"
CONDITIONS = ["sunny", "partlycloudy", "cloudy", "fog", "rainy", "pouring", "lightning", "lightning-rainy",
              "snowy", "snowy-rainy", "hail"]
OKTA_PCT = {"SKC": 0, "CLR": 0, "NSC": 0, "NCD": 0, "CAVOK": 0, "FEW": 19, "SCT": 44, "BKN": 75, "OVC": 100,
            "OVX": 100, "VV": 100}


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def http_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "ha-airport-weather/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def supervisor(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    return http_json("http://supervisor" + path, body,
                     {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})


# ---------------------------------------------------------------- METAR -> HA
def condition(m):
    """HA condition, day form (sunny at night means clear)."""
    wx = (m.get("wxString") or "").upper()
    heavy = "+" in wx
    if "TS" in wx:
        if "GR" in wx or "GS" in wx:
            return "hail"
        return "lightning-rainy" if any(p in wx for p in ("RA", "DZ", "SH")) else "lightning"
    if "GR" in wx or "GS" in wx:
        return "hail"
    if "SN" in wx:
        return "snowy-rainy" if "RA" in wx else "snowy"
    if any(p in wx for p in ("RA", "DZ", "SH")):
        return "pouring" if heavy and "RA" in wx else "rainy"
    if "FG" in wx:
        return "fog"
    pct = cloud_pct(m)
    if pct >= 75:
        return "cloudy"
    if pct >= 44:
        return "partlycloudy"
    return "sunny"   # clear / FEW


def cloud_pct(m):
    covers = [c.get("cover") for c in (m.get("clouds") or [])] or [m.get("cover") or "CLR"]
    return max(OKTA_PCT.get(c, 0) for c in covers)


def humidity(t, td):
    if t is None or td is None:
        return None
    f = lambda x: math.exp(17.625 * x / (243.04 + x))
    return round(100 * f(td) / f(t))


def visibility_km(v):
    if v is None:
        return None
    if isinstance(v, str):   # "10+" statute miles
        v = float(v.rstrip("+"))
    return round(v * 1.609344, 1)


def kmh(kt):
    return None if kt is None else round(kt * 1.852, 1)


def payload(m):
    clouds = ", ".join(f"{c['cover']} {c['base']} ft" if c.get("base") else c["cover"] for c in (m.get("clouds") or []))
    wdir = m.get("wdir")
    return {
        "condition": condition(m),
        "cloud_coverage": cloud_pct(m),
        "temperature": m.get("temp"),
        "dew_point": m.get("dewp"),
        "humidity": humidity(m.get("temp"), m.get("dewp")),
        "pressure": m.get("altim"),
        "wind_speed": kmh(m.get("wspd")),
        "wind_gust": kmh(m.get("wgst")) or kmh(m.get("wspd")),
        "wind_bearing": wdir if isinstance(wdir, (int, float)) else None,   # "VRB" = variable
        "visibility": visibility_km(m.get("visib")),
        "observed": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime(m["obsTime"])),
        "raw": m.get("rawOb", ""),
        "weather": m.get("wxString") or "",
        "clouds": clouds or "clear",
        "station": m.get("name", STATION),
    }


# ---------------------------------------------------------------- discovery
SENSORS = [
    # key, name, unit, device_class, state_class, icon, extra
    ("condition", "Condition", None, "enum", None, "mdi:weather-partly-cloudy",
     {"options": CONDITIONS, "json_attributes_topic": STATE,
      "json_attributes_template": "{{ {'raw': value_json.raw, 'weather': value_json.weather, "
                                  "'clouds': value_json.clouds, 'station': value_json.station} | tojson }}"}),
    ("cloud_coverage", "Cloud coverage", "%", None, "measurement", "mdi:cloud-percent", {}),
    ("temperature", "Temperature", "°C", "temperature", "measurement", None, {}),
    ("dew_point", "Dew point", "°C", "temperature", "measurement", None, {}),
    ("humidity", "Humidity", "%", "humidity", "measurement", None, {}),
    ("pressure", "Pressure", "hPa", "atmospheric_pressure", "measurement", None, {}),
    ("wind_speed", "Wind speed", "km/h", "wind_speed", "measurement", None, {}),
    ("wind_gust", "Wind gust", "km/h", "wind_speed", "measurement", None, {}),
    ("wind_bearing", "Wind bearing", "°", "wind_direction", "measurement_angle", None, {}),
    ("visibility", "Visibility", "km", "distance", "measurement", "mdi:eye", {}),
    ("observed", "Observed", None, "timestamp", None, None, {}),
    ("raw", "METAR", None, None, None, "mdi:airplane", {}),
]


def device():
    return {"identifiers": [UID], "name": f"Airport Weather {STATION}", "manufacturer": "aviationweather.gov",
            "model": "METAR", "suggested_area": "Outside"}


def publish_discovery(c):
    for key, name, unit, dc, sc, icon, extra in SENSORS:
        cfg = {"name": name, "unique_id": f"{UID}_{key}", "default_entity_id": f"sensor.{PREFIX}_{key}",
               "state_topic": STATE, "value_template": f"{{{{ value_json.{key} }}}}",
               "availability_topic": AVAIL, "device": device(), **extra}
        if unit:
            cfg["unit_of_measurement"] = unit
        if dc:
            cfg["device_class"] = dc
        if sc:
            cfg["state_class"] = sc
        if icon:
            cfg["icon"] = icon
        c.publish(f"homeassistant/sensor/{UID}/{key}/config", json.dumps(cfg), qos=1, retain=True)
    c.publish(AVAIL, "online", qos=1, retain=True)


# ---------------------------------------------------------------- loops
def metar_loop(c):
    last = None
    while True:
        try:
            data = http_json(f"https://aviationweather.gov/api/data/metar?format=json&ids={STATION}")
            if data:
                p = payload(data[0])
                c.publish(STATE, json.dumps(p), qos=1, retain=True)
                if p["raw"] != last:
                    log("METAR", p["raw"], "->", p["condition"])
                    last = p["raw"]
            else:
                log("no METAR returned for", STATION)
        except Exception as e:
            log("METAR fetch failed:", e)
        time.sleep(POLL)


def main():
    m = supervisor("/services/mqtt")["data"]
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"airport_weather_{STATION.lower()}")
    if m.get("username"):
        c.username_pw_set(m["username"], m.get("password"))
    c.will_set(AVAIL, "offline", qos=1, retain=True)

    def on_connect(cl, _u, _f, rc, _p=None):
        log("MQTT connected", rc)
        cl.subscribe("homeassistant/status")
        publish_discovery(cl)

    def on_message(cl, _u, msg):
        if msg.topic == "homeassistant/status" and msg.payload == b"online":
            publish_discovery(cl)

    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(m["host"], int(m["port"]))
    c.loop_start()
    log(f"station {STATION}, poll {POLL}s")
    metar_loop(c)


if __name__ == "__main__":
    main()
