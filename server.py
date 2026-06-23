#!/usr/bin/env python3
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent / "static"
ENV_FILE = Path(__file__).resolve().parent / ".env"
SYDNEY = ZoneInfo("Australia/Sydney")


def load_local_env():
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_local_env()

LAT = float(os.getenv("DASHBOARD_LAT", "-33.8846"))
LON = float(os.getenv("DASHBOARD_LON", "151.2119"))
TFNSW_KEY = os.getenv("TFNSW_API_KEY", "").strip()
TFNSW_BASE = os.getenv("TFNSW_BASE", "https://api.transport.nsw.gov.au/v1/tp")
WATCHED_LINES = {
    "train": tuple(v.upper() for v in os.getenv("DASHBOARD_TRAIN_LINES", "T8").split(",") if v.strip()),
    "metro": tuple(v.upper() for v in os.getenv("DASHBOARD_METRO_LINES", "M1").split(",") if v.strip()),
    "light_rail": tuple(v.upper() for v in os.getenv("DASHBOARD_LIGHT_RAIL_LINES", "L2,L3").split(",") if v.strip()),
}
WATCHED_DESTINATIONS = {
    "train": tuple(v.lower() for v in os.getenv("DASHBOARD_TRAIN_DESTINATIONS", "").split(",") if v.strip()),
    "metro": tuple(v.lower() for v in os.getenv("DASHBOARD_METRO_DESTINATIONS", "").split(",") if v.strip()),
    "light_rail": tuple(v.lower() for v in os.getenv("DASHBOARD_LIGHT_RAIL_DESTINATIONS", "").split(",") if v.strip()),
}
CENTRAL_STOP_IDS = {"200060", "2000448", "2000447"}
TRAIN_PLATFORMS = tuple(
    v.strip().upper()
    for v in os.getenv("DASHBOARD_TRAIN_PLATFORMS", "CE16,CE17,CE24,CE18,CE19,CE23").split(",")
    if v.strip()
)
TRAIN_MAX_DUE_MINUTES = int(os.getenv("DASHBOARD_TRAIN_MAX_DUE_MINUTES", "180"))
WEATHER_CACHE_SECONDS = int(os.getenv("DASHBOARD_WEATHER_CACHE_SECONDS", "300"))
ALERT_CACHE_SECONDS = int(os.getenv("DASHBOARD_ALERT_CACHE_SECONDS", "600"))
DEPARTURE_CACHE_SECONDS = 45
DIRECTION_QUERY_LIMIT = 8
TRAIN_PLATFORM_QUERY_LIMIT = 4
TRAIN_STOPS_LOOKBACK_MINUTES = 10
TRAIN_STOPS_TRIP_CANDIDATES = 12
TRAIN_PLATFORM_META = {
    "CE16": {"id": "2000336", "name": "16", "kind": "North Shore", "hint": "T1 / T9", "lines": ("T1", "T9"), "line_ids": ("nsw:020T1:N:H:", "nsw:020T9: :H:"), "terms": ("north shore", "gordon", "hornsby")},
    "CE17": {"id": "2000337", "name": "17", "kind": "City Circle", "hint": "T2 / T8", "lines": ("T2", "T8"), "line_ids": ("nsw:020T2: :H:", "nsw:020T8: :H:"), "terms": ("city circle", "town hall", "airport")},
    "CE18": {"id": "2000338", "name": "18", "kind": "West / Northern", "hint": "T1 / T9", "lines": ("T1", "T9"), "line_ids": ("nsw:020T1:W:H:", "nsw:020T9: :H:"), "terms": ("western", "northern", "strathfield", "parramatta")},
    "CE19": {"id": "2000339", "name": "19", "kind": "Inner West", "hint": "T2 / T3", "lines": ("T2", "T3"), "line_ids": ("nsw:020T2: :H:", "nsw:020T3: :H:"), "terms": ("inner west", "strathfield", "parramatta", "liverpool")},
    "CE23": {"id": "2000343", "name": "23", "kind": "Airport", "hint": "T8", "lines": ("T8",), "line_ids": ("nsw:020T8: :H:",), "terms": ("airport", "revesby", "macarthur")},
    "CE24": {"id": "2000344", "name": "24", "kind": "Bondi", "hint": "T4", "lines": ("T4",), "line_ids": ("nsw:020T4: :R:", "nsw:02SCO: :R:"), "terms": ("bondi", "illawarra", "south coast")},
}
TRAIN_ALERT_LINES = tuple(sorted({
    line
    for meta in TRAIN_PLATFORM_META.values()
    for line in meta.get("lines", ())
}))
CITY_CIRCLE_STOPS = {
    "town hall": ["Town Hall", "Wynyard", "Circular Quay", "St James", "Museum", "Central"],
    "museum": ["Museum", "St James", "Circular Quay", "Wynyard", "Town Hall", "Central"],
}
TRAIN_STOP_TEMPLATES = {
    "CE16": {
        "T1": {
            "berowra": ["Town Hall", "Wynyard", "Milsons Point", "North Sydney", "Waverton", "Wollstonecraft", "St Leonards", "Artarmon", "Chatswood", "Roseville", "Lindfield", "Killara", "Gordon", "Pymble", "Turramurra", "Warrawee", "Wahroonga", "Waitara", "Hornsby", "Asquith", "Mount Colah", "Mount Kuring-gai", "Berowra"],
            "chatswood": ["Town Hall", "Wynyard", "Milsons Point", "North Sydney", "Waverton", "Wollstonecraft", "St Leonards", "Artarmon", "Chatswood"],
            "gordon": ["Town Hall", "Wynyard", "Milsons Point", "North Sydney", "Waverton", "Wollstonecraft", "St Leonards", "Artarmon", "Chatswood", "Roseville", "Lindfield", "Killara", "Gordon"],
            "hornsby": ["Town Hall", "Wynyard", "Milsons Point", "North Sydney", "Waverton", "Wollstonecraft", "St Leonards", "Artarmon", "Chatswood", "Roseville", "Lindfield", "Killara", "Gordon", "Pymble", "Turramurra", "Warrawee", "Wahroonga", "Waitara", "Hornsby"],
            "lindfield": ["Town Hall", "Wynyard", "Milsons Point", "North Sydney", "Waverton", "Wollstonecraft", "St Leonards", "Artarmon", "Chatswood", "Roseville", "Lindfield"],
            "north sydney": ["Town Hall", "Wynyard", "Milsons Point", "North Sydney"],
        },
        "T9": {
            "gordon": ["Town Hall", "Wynyard", "Milsons Point", "North Sydney", "Waverton", "Wollstonecraft", "St Leonards", "Artarmon", "Chatswood", "Roseville", "Lindfield", "Killara", "Gordon"],
            "north sydney": ["Town Hall", "Wynyard", "Milsons Point", "North Sydney"],
        },
    },
    "CE17": {
        "T2": {
            "museum": ["Town Hall", "Wynyard", "Circular Quay", "St James", "Museum"],
            "redfern": ["Town Hall", "Wynyard", "Circular Quay", "St James", "Museum", "Redfern"],
        },
        "T8": {
            "campbelltown": ["Town Hall", "Wynyard", "Circular Quay", "St James", "Museum", "Redfern", "Erskineville", "St Peters", "Sydenham", "Revesby", "Panania", "East Hills", "Holsworthy", "Glenfield", "Macquarie Fields", "Ingleburn", "Minto", "Leumeah", "Campbelltown"],
            "sydenham": ["Town Hall", "Wynyard", "Circular Quay", "St James", "Museum", "Redfern", "Erskineville", "St Peters", "Sydenham"],
        },
    },
    "CE18": {
        "T1": {
            "blacktown": ["Redfern", "Strathfield", "Lidcombe", "Parramatta", "Westmead", "Wentworthville", "Pendle Hill", "Toongabbie", "Seven Hills", "Blacktown"],
            "emu plains": ["Redfern", "Strathfield", "Lidcombe", "Auburn", "Clyde", "Granville", "Harris Park", "Parramatta", "Westmead", "Wentworthville", "Pendle Hill", "Toongabbie", "Seven Hills", "Blacktown", "Doonside", "Rooty Hill", "Mount Druitt", "St Marys", "Werrington", "Kingswood", "Penrith", "Emu Plains"],
            "penrith": ["Redfern", "Strathfield", "Flemington", "Lidcombe", "Auburn", "Clyde", "Granville", "Harris Park", "Parramatta", "Westmead", "Wentworthville", "Pendle Hill", "Toongabbie", "Seven Hills", "Blacktown", "Doonside", "Rooty Hill", "Mount Druitt", "St Marys", "Werrington", "Kingswood", "Penrith"],
            "richmond": ["Redfern", "Strathfield", "Lidcombe", "Granville", "Parramatta", "Westmead", "Wentworthville", "Pendle Hill", "Toongabbie", "Seven Hills", "Blacktown", "Marayong", "Quakers Hill", "Schofields", "Riverstone", "Vineyard", "Mulgrave", "Windsor", "Clarendon", "East Richmond", "Richmond"],
            "schofields": ["Redfern", "Strathfield", "Lidcombe", "Parramatta", "Westmead", "Wentworthville", "Pendle Hill", "Toongabbie", "Seven Hills", "Blacktown", "Marayong", "Quakers Hill", "Schofields"],
        },
        "T9": {
            "berowra": ["Redfern", "Burwood", "Strathfield", "North Strathfield", "Concord West", "Rhodes", "Meadowbank", "West Ryde", "Denistone", "Eastwood", "Epping", "Cheltenham", "Beecroft", "Pennant Hills", "Thornleigh", "Normanhurst", "Hornsby", "Asquith", "Mount Colah", "Mount Kuring-gai", "Berowra"],
            "epping": ["Redfern", "Strathfield", "North Strathfield", "Concord West", "Rhodes", "Meadowbank", "West Ryde", "Denistone", "Eastwood", "Epping"],
            "hornsby": ["Redfern", "Ashfield", "Croydon", "Burwood", "Strathfield", "North Strathfield", "Concord West", "Rhodes", "Meadowbank", "West Ryde", "Denistone", "Eastwood", "Epping", "Cheltenham", "Beecroft", "Pennant Hills", "Thornleigh", "Normanhurst", "Hornsby"],
        },
    },
    "CE19": {
        "T2": {
            "ashfield": ["Redfern", "Macdonaldtown", "Newtown", "Stanmore", "Petersham", "Lewisham", "Summer Hill", "Ashfield"],
            "fairfield": ["Redfern", "Newtown", "Ashfield", "Burwood", "Strathfield", "Homebush", "Flemington", "Lidcombe", "Auburn", "Clyde", "Granville", "Merrylands", "Guildford", "Yennora", "Fairfield"],
            "glenfield": ["Redfern", "Newtown", "Ashfield", "Burwood", "Strathfield", "Flemington", "Lidcombe", "Auburn", "Clyde", "Granville", "Merrylands", "Guildford", "Yennora", "Fairfield", "Canley Vale", "Cabramatta", "Warwick Farm", "Liverpool", "Casula", "Glenfield"],
            "homebush": ["Redfern", "Macdonaldtown", "Newtown", "Stanmore", "Petersham", "Lewisham", "Summer Hill", "Ashfield", "Croydon", "Burwood", "Strathfield", "Homebush"],
            "leppington": ["Redfern", "Newtown", "Lewisham", "Summer Hill", "Ashfield", "Croydon", "Burwood", "Strathfield", "Flemington", "Lidcombe", "Auburn", "Clyde", "Granville", "Merrylands", "Guildford", "Yennora", "Fairfield", "Canley Vale", "Cabramatta", "Warwick Farm", "Liverpool", "Casula", "Glenfield", "Edmondson Park", "Leppington"],
            "liverpool": ["Redfern", "Macdonaldtown", "Newtown", "Stanmore", "Petersham", "Lewisham", "Summer Hill", "Ashfield", "Croydon", "Burwood", "Strathfield", "Homebush", "Flemington", "Lidcombe", "Granville", "Merrylands", "Guildford", "Yennora", "Fairfield", "Canley Vale", "Cabramatta", "Warwick Farm", "Liverpool"],
            "macarthur": ["Redfern", "Newtown", "Ashfield", "Burwood", "Strathfield", "Homebush", "Flemington", "Lidcombe", "Auburn", "Granville", "Merrylands", "Guildford", "Yennora", "Fairfield", "Canley Vale", "Cabramatta", "Warwick Farm", "Liverpool", "Casula", "Glenfield", "Macquarie Fields", "Ingleburn", "Minto", "Leumeah", "Campbelltown", "Macarthur"],
            "parramatta": ["Redfern", "Macdonaldtown", "Newtown", "Stanmore", "Petersham", "Lewisham", "Summer Hill", "Ashfield", "Croydon", "Burwood", "Strathfield", "Homebush", "Flemington", "Lidcombe", "Auburn", "Clyde", "Granville", "Harris Park", "Parramatta"],
            "redfern": ["Redfern"],
        },
        "T3": {
            "liverpool": ["Redfern", "Macdonaldtown", "Newtown", "Stanmore", "Petersham", "Lewisham", "Summer Hill", "Ashfield", "Croydon", "Burwood", "Strathfield", "Homebush", "Flemington", "Lidcombe", "Berala", "Regents Park", "Sefton", "Chester Hill", "Leightonfield", "Villawood", "Carramar", "Cabramatta", "Warwick Farm", "Liverpool"],
        },
    },
    "CE23": {
        "T8": {
            "macarthur": ["Green Square", "Mascot", "Domestic Airport", "International Airport", "Wolli Creek", "Turrella", "Bardwell Park", "Bexley North", "Kingsgrove", "Beverly Hills", "Narwee", "Riverwood", "Padstow", "Revesby", "Panania", "East Hills", "Holsworthy", "Glenfield", "Macquarie Fields", "Ingleburn", "Minto", "Leumeah", "Campbelltown", "Macarthur"],
            "revesby": ["Green Square", "Mascot", "Domestic Airport", "International Airport", "Wolli Creek", "Turrella", "Bardwell Park", "Bexley North", "Kingsgrove", "Beverly Hills", "Narwee", "Riverwood", "Padstow", "Revesby"],
            "sydenham": ["Redfern", "Erskineville", "St Peters", "Sydenham"],
            "turrella": ["Green Square", "Mascot", "Domestic Airport", "International Airport", "Wolli Creek", "Turrella"],
        },
    },
    "CE24": {
        "T4": {
            "bondi junction": ["Town Hall", "Martin Place", "Kings Cross", "Edgecliff", "Bondi Junction"],
        },
    },
}
STOPS = [
    {"name": "Train", "kind": "Central platforms", "mode": "train_platforms"},
    {
        "name": "Metro",
        "kind": "Central",
        "mode": "metro",
        "directions": [
            {"id": "tallawong", "title": "Tallawong", "stopId": "2000466", "noticeTerms": ("tallawong", "chatswood", "epping", "rouse hill", "castle hill")},
            {"id": "sydenham", "title": "Sydenham", "stopId": "2000467", "noticeTerms": ("sydenham", "central", "martin place", "waterloo", "gadigal")},
        ],
    },
    {
        "name": "Light Rail",
        "kind": "Central Chalmers St",
        "mode": "light_rail",
        "directions": [
            {"id": "circular_quay", "title": "Circular Quay", "stopId": "2000448", "noticeTerms": ("circular quay", "cq")},
            {"id": "randwick_kingsford", "title": "Randwick / Kingsford", "stopId": "2000447", "noticeTerms": ("randwick", "kingsford")},
        ],
    },
]

cache = {}


def now_sydney():
    return datetime.now(SYDNEY)


def fetch_json(url, headers=None, timeout=8):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def cached(key, ttl, loader):
    current = time.time()
    entry = cache.get(key)
    if entry and current - entry["time"] < ttl:
        return entry["value"]
    value = loader()
    cache[key] = {"time": current, "value": value}
    return value


def weather_code_label(code):
    labels = {
        0: "Clear",
        1: "Mostly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Fog",
        51: "Light drizzle",
        53: "Drizzle",
        55: "Heavy drizzle",
        61: "Light rain",
        63: "Rain",
        65: "Heavy rain",
        80: "Showers",
        81: "Showers",
        82: "Heavy showers",
        95: "Thunderstorm",
    }
    return labels.get(int(code or 0), "Weather")


def weather_code_icon(code):
    icons = {
        0: "☀",
        1: "☀",
        2: "◐",
        3: "☁",
        45: "≋",
        48: "≋",
        51: "☂",
        53: "☂",
        55: "☂",
        61: "☂",
        63: "☂",
        65: "☂",
        80: "☂",
        81: "☂",
        82: "☂",
        95: "⚡",
    }
    return icons.get(int(code or 0), "○")


def load_weather():
    now = now_sydney()
    params = {
        "latitude": LAT,
        "longitude": LON,
        "timezone": "Australia/Sydney",
        "current": ",".join([
            "temperature_2m",
            "apparent_temperature",
            "relative_humidity_2m",
            "precipitation",
            "weather_code",
            "wind_speed_10m",
            "wind_gusts_10m",
        ]),
        "hourly": "temperature_2m,precipitation_probability,precipitation,weather_code",
        "forecast_days": "2",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    data = fetch_json(url)
    current = data.get("current", {})
    hourly = []
    hourly_data = data.get("hourly", {})
    times = hourly_data.get("time", [])
    start = 0
    for i, stamp in enumerate(times):
        try:
            hour_dt = datetime.fromisoformat(stamp).replace(tzinfo=SYDNEY)
        except ValueError:
            continue
        if hour_dt >= now.replace(minute=0, second=0, microsecond=0):
            start = i
            break
    for i, stamp in enumerate(times[start:start + 8], start=start):
        try:
            hour = datetime.fromisoformat(stamp).strftime("%H:%M")
        except ValueError:
            hour = stamp[-5:]
        hourly.append({
            "time": hour,
            "temp": hourly_data.get("temperature_2m", [None] * len(times))[i],
            "rainChance": hourly_data.get("precipitation_probability", [None] * len(times))[i],
            "rain": hourly_data.get("precipitation", [None] * len(times))[i],
            "code": hourly_data.get("weather_code", [None] * len(times))[i],
        })
    current_code = current.get("weather_code")
    return {
        "temp": current.get("temperature_2m"),
        "feels": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "rain": current.get("precipitation"),
        "wind": current.get("wind_speed_10m"),
        "gust": current.get("wind_gusts_10m"),
        "summary": weather_code_label(current_code),
        "icon": weather_code_icon(current_code),
        "hourly": hourly[:8],
    }


def tfnsw_headers():
    return {
        "Authorization": f"apikey {TFNSW_KEY}",
        "Accept": "application/json",
        "User-Agent": "mireader-dashboard/1.0",
    }


def load_departures(stop):
    if not TFNSW_KEY:
        raise RuntimeError("TFNSW_API_KEY is not configured")
    if stop.get("mode") == "train_platforms":
        return load_train_platforms()
    if stop.get("directions"):
        return load_directional_departures(stop)
    rows = []
    for stop_id in stop_ids(stop):
        rows.extend(load_departures_for_stop(stop, stop_id))
    rows.sort(key=departure_sort_key)
    return rows[:8]


def stop_ids(stop):
    return [part.strip() for part in str(stop["id"]).split(",") if part.strip()]


def load_directional_departures(stop):
    directions = []
    for direction in stop.get("directions", []):
        stop_id = direction.get("stopId")
        if not stop_id:
            raise RuntimeError(f"Missing stop id for {stop.get('name')} {direction.get('title')}")
        rows = load_departures_for_stop(stop, stop_id, limit=DIRECTION_QUERY_LIMIT, query_limit=20)
        directions.append({
            "id": direction.get("id") or stop_id,
            "title": direction.get("title") or direction.get("id") or stop_id,
            "departures": rows,
        })
    return directions


def departure_monitor_url(stop_id, limit):
    now = now_sydney()
    params = {
        "outputFormat": "rapidJSON",
        "coordOutputFormat": "EPSG:4326",
        "mode": "direct",
        "type_dm": "stop",
        "name_dm": stop_id,
        "itdDate": now.strftime("%Y%m%d"),
        "itdTime": now.strftime("%H%M"),
        "departureMonitorMacro": "true",
        "TfNSWDM": "true",
        "limit": str(limit),
    }
    return f"{TFNSW_BASE}/departure_mon?" + urllib.parse.urlencode(params)


def load_departures_for_stop(stop, stop_id, limit=8, query_limit=20):
    mode = stop.get("mode")
    url = departure_monitor_url(stop_id, query_limit)
    data = fetch_json(url, headers=tfnsw_headers())
    events = data.get("stopEvents", [])
    rows = []
    for event in events:
        trans = event.get("transportation", {})
        line = trans.get("number") or trans.get("disassembledName") or trans.get("name") or ""
        destination = trans.get("destination", {}).get("name") or trans.get("description") or ""
        if not matches_stop_mode(line, destination, mode):
            continue
        planned = event.get("departureTimePlanned") or event.get("arrivalTimePlanned")
        estimated = event.get("departureTimeEstimated") or event.get("arrivalTimeEstimated") or planned
        rows.append({
            "line": line,
            "destination": destination,
            "planned": planned,
            "estimated": estimated,
            "due": minutes_until(estimated or planned),
            "realtime": bool(event.get("departureTimeEstimated") or event.get("arrivalTimeEstimated")),
        })
        if len(rows) >= limit:
            break
    return rows


def load_train_platforms():
    platforms = []
    for platform in TRAIN_PLATFORMS:
        meta = TRAIN_PLATFORM_META.get(platform, {})
        stop_id = meta.get("id")
        if not stop_id:
            raise RuntimeError(f"Missing stop id for platform {platform}")
        rows = load_train_platform_departures(platform, stop_id)
        rows.sort(key=departure_sort_key)
        rows = rows[:TRAIN_PLATFORM_QUERY_LIMIT]
        if rows:
            rows[0]["stops"] = train_next_stops(rows[0], stop_id)
            rows[0]["service"] = train_service_pattern(rows[0], rows[0]["stops"])
        platforms.append({
            "id": platform,
            "name": meta.get("name") or platform_label(platform),
            "kind": meta.get("kind") or "Central",
            "hint": meta.get("hint") or "",
            "departures": rows,
        })
    return platforms


def load_train_platform_departures(platform, stop_id):
    url = departure_monitor_url(stop_id, 20)
    data = fetch_json(url, headers=tfnsw_headers())
    rows = []
    for event in data.get("stopEvents", []):
        row = train_platform_departure(event)
        if row and row["platform"] == platform and train_departure_is_current(row):
            rows.append(row)
    return rows


def train_departure_is_current(row):
    time_value = departure_time(row)
    if not time_value:
        return True
    try:
        dt = datetime.fromisoformat(time_value.replace("Z", "+00:00")).astimezone(SYDNEY)
    except ValueError:
        return True
    return (dt - now_sydney()).total_seconds() <= TRAIN_MAX_DUE_MINUTES * 60


def departure_time(row):
    return row.get("estimated") or row.get("planned") or ""


def departure_sort_key(row):
    return departure_time(row) or "9999"


def platform_label(platform):
    return re.sub(r"^(CE|SD)", "", str(platform or ""))


def train_platform_departure(event):
    trans = event.get("transportation") or {}
    product = trans.get("product") or {}
    operator = trans.get("operator") or {}
    if not is_train_product(product.get("name"), operator.get("name")):
        return None

    location = event.get("location") or {}
    props = location.get("properties") or {}
    event_props = event.get("properties") or {}
    platform = str(props.get("platform") or "").upper()
    if not platform:
        return None

    line = trans.get("number") or trans.get("disassembledName") or trans.get("name") or ""
    destination = trans.get("destination", {}).get("name") or trans.get("description") or ""
    destination_id = trans.get("destination", {}).get("id") or ""
    planned = event.get("departureTimePlanned") or event.get("arrivalTimePlanned")
    estimated = event.get("departureTimeEstimated") or event.get("arrivalTimeEstimated") or planned
    return {
        "line": line,
        "transportId": trans.get("id") or "",
        "realtimeTripId": event_props.get("RealtimeTripId") or event_props.get("AVMSTripID") or "",
        "gtfsTripId": (trans.get("properties") or {}).get("gtfsTripId") or "",
        "destination": destination,
        "destinationId": destination_id,
        "platform": platform,
        "planned": planned,
        "estimated": estimated,
        "due": minutes_until(estimated or planned),
        "realtime": bool(event.get("departureTimeEstimated") or event.get("arrivalTimeEstimated")),
        "service": "",
    }


def train_next_stops(row, stop_id):
    city_circle_stops = city_circle_stop_sequence(row)
    if city_circle_stops:
        return city_circle_stops
    destination_id = row.get("destinationId")
    planned = row.get("planned") or row.get("estimated")
    if not destination_id or not planned:
        return []
    key = f"train-stops:v4:{stop_id}:{destination_id}:{planned}:{row.get('realtimeTripId', '')}:{row.get('gtfsTripId', '')}"
    try:
        return cached(key, 300, lambda: fetch_train_next_stops(stop_id, destination_id, planned, row))
    except Exception:
        return []


def city_circle_stop_sequence(row):
    destination = str(row.get("destination") or "").lower()
    if "city circle" not in destination:
        return []
    for via, stops in CITY_CIRCLE_STOPS.items():
        if via in destination:
            return stops
    return []


def fetch_train_next_stops(stop_id, destination_id, planned, row):
    try:
        dt = datetime.fromisoformat(str(planned).replace("Z", "+00:00")).astimezone(SYDNEY)
    except ValueError:
        return []
    query_dt = dt - timedelta(minutes=TRAIN_STOPS_LOOKBACK_MINUTES)
    params = {
        "outputFormat": "rapidJSON",
        "coordOutputFormat": "EPSG:4326",
        "depArrMacro": "dep",
        "type_origin": "stop",
        "name_origin": stop_id,
        "type_destination": "stop",
        "name_destination": destination_id,
        "itdDate": query_dt.strftime("%Y%m%d"),
        "itdTime": query_dt.strftime("%H%M"),
        "calcNumberOfTrips": str(TRAIN_STOPS_TRIP_CANDIDATES),
        "TfNSWTR": "true",
        "maxChanges": "0",
    }
    url = f"{TFNSW_BASE}/trip?" + urllib.parse.urlencode(params)
    data = fetch_json(url, headers=tfnsw_headers(), timeout=10)
    journeys = data.get("journeys") or []
    if not journeys:
        return []
    for leg in matching_train_legs(journeys, row):
        sequence = leg.get("stopSequence") or []
        stops = [clean_train_stop_name(stop) for stop in sequence[1:]]
        stops = [stop for stop in stops if stop and stop.lower() != "central"]
        if stops:
            return stops
    return []


def matching_train_legs(journeys, row):
    row_line = short_line(row.get("line"))
    row_platform = str(row.get("platform") or "").upper()
    row_transport_id = str(row.get("transportId") or "")
    row_realtime_trip_id = str(row.get("realtimeTripId") or "")
    row_gtfs_trip_id = str(row.get("gtfsTripId") or "")
    for journey in journeys:
        for leg in journey.get("legs") or []:
            trans = leg.get("transportation") or {}
            product = trans.get("product") or {}
            operator = trans.get("operator") or {}
            if not is_train_product(product.get("name"), operator.get("name")):
                continue
            sequence = leg.get("stopSequence") or []
            if len(sequence) < 3:
                continue
            trans_props = trans.get("properties") or {}
            leg_realtime_trip_id = str(trans_props.get("RealtimeTripId") or trans_props.get("AVMSTripID") or "")
            if row_realtime_trip_id and leg_realtime_trip_id and row_realtime_trip_id == leg_realtime_trip_id:
                yield leg
                continue
            leg_gtfs_trip_id = str(trans_props.get("gtfsTripId") or "")
            if row_gtfs_trip_id and leg_gtfs_trip_id and row_gtfs_trip_id == leg_gtfs_trip_id:
                yield leg
                continue
            origin = leg.get("origin") or {}
            origin_props = origin.get("properties") or {}
            origin_platform = str(origin_props.get("platform") or "").upper()
            if row_platform and origin_platform and origin_platform != row_platform:
                continue
            leg_line = short_line(trans.get("number") or trans.get("disassembledName") or trans.get("name"))
            if row_line and leg_line and row_line != leg_line:
                continue
            leg_transport_id = str(trans.get("id") or "")
            if row_transport_id and leg_transport_id and row_transport_id.split(":")[:4] != leg_transport_id.split(":")[:4]:
                continue
            yield leg


def short_line(line):
    match = re.match(r"^([TLM]\d+)", str(line or ""), flags=re.I)
    return match.group(1).upper() if match else str(line or "").upper()


def clean_train_stop_name(stop):
    stop = stop or {}
    name = str(stop.get("name") or stop.get("disassembledName") or "")
    name = re.sub(r"\s+Station\b.*$", "", name)
    name = re.sub(r"\s*,\s*Platform\b.*$", "", name)
    name = re.sub(r"\s*,\s*[^,]+$", "", name)
    return " ".join(name.split())


def is_train_product(product_name, operator_name):
    product_name = str(product_name or "")
    operator_name = str(operator_name or "")
    if any(term in product_name for term in ("Metro", "Light Rail", "Bus", "buses")):
        return False
    return "Train" in product_name or operator_name in ("Sydney Trains", "NSW Trains", "NSW TrainLink")


def train_service_pattern(row, stops):
    template = train_stop_template(row, stops)
    if not template or not stops:
        return ""
    if contains_stop_sequence(stops, template):
        return "All stops"
    return "Limited"


def train_stop_template(row, stops):
    if city_circle_stop_sequence(row):
        return city_circle_stop_sequence(row)
    platform = str(row.get("platform") or "").upper()
    line = short_line(row.get("line"))
    platform_templates = TRAIN_STOP_TEMPLATES.get(platform) or {}
    line_templates = platform_templates.get(line) or {}
    for destination in train_destination_candidates(row, stops):
        template = line_templates.get(destination)
        if template:
            return template
    return []


def train_destination_candidates(row, stops):
    candidates = []
    if stops:
        candidates.append(stops[-1])
    destination = str(row.get("destination") or "")
    if destination:
        candidates.append(re.sub(r"\s+via\s+.+$", "", destination, flags=re.I))
        candidates.append(destination)
    seen = set()
    for candidate in candidates:
        key = normalize_stop_name(candidate)
        if key and key not in seen:
            seen.add(key)
            yield key


def contains_stop_sequence(actual, expected):
    actual_names = [normalize_stop_name(stop) for stop in actual]
    actual_names = [name for name in actual_names if name]
    expected_names = [normalize_stop_name(stop) for stop in expected]
    expected_names = [name for name in expected_names if name]
    index = 0
    for stop in actual_names:
        if index < len(expected_names) and stop == expected_names[index]:
            index += 1
    return bool(expected_names) and index == len(expected_names)


def normalize_stop_name(value):
    value = re.sub(r"\s+Station\b.*$", "", str(value or ""), flags=re.I)
    value = re.sub(r"\s*,\s*Platform\b.*$", "", value, flags=re.I)
    value = re.sub(r"\s*,\s*[^,]+$", "", value)
    return " ".join(value.lower().split())


def matches_stop_mode(line, destination, mode):
    line = str(line or "").strip().upper()
    destination = str(destination or "").strip().lower()
    if not mode:
        return True
    if not matches_watched_destination(destination, mode):
        return False
    if mode == "metro":
        return line_matches_watched(line, mode) if WATCHED_LINES[mode] else line.startswith("M")
    if mode == "light_rail":
        return line_matches_watched(line, mode) if WATCHED_LINES[mode] else line.startswith("L")
    if mode == "train":
        if line.startswith(("M", "L")):
            return False
        return line_matches_watched(line, mode) if WATCHED_LINES[mode] else True
    return True


def line_matches_watched(line, mode):
    line = str(line or "").upper()
    return any(watched in line for watched in WATCHED_LINES.get(mode, ()))


def matches_watched_destination(destination, mode):
    terms = WATCHED_DESTINATIONS.get(mode, ())
    if not terms:
        return True
    destination = str(destination or "").lower()
    return any(term in destination for term in terms)


def minutes_until(iso_value):
    if not iso_value:
        return None
    try:
        dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00")).astimezone(SYDNEY)
        return max(0, round((dt - now_sydney()).total_seconds() / 60))
    except ValueError:
        return None


def load_alerts():
    if not TFNSW_KEY:
        raise RuntimeError("TFNSW_API_KEY is not configured")
    params = {
        "outputFormat": "rapidJSON",
        "coordOutputFormat": "EPSG:4326",
        "filterDateValid": now_sydney().strftime("%d-%m-%Y"),
        "filterPublicationStatus": "current",
    }
    url = f"{TFNSW_BASE}/add_info?" + urllib.parse.urlencode(params)
    data = fetch_json(url, headers=tfnsw_headers())
    infos = data.get("infos") or data.get("messages") or data.get("stopEvents") or []
    if isinstance(infos, dict):
        infos = infos.get("current") or []
    if not isinstance(infos, list):
        infos = []
    candidates = []
    seen = set()
    for info in infos:
        if not isinstance(info, dict):
            continue
        if not is_relevant_alert(info):
            continue
        text = alert_title(info)
        if text and text not in seen:
            seen.add(text)
            candidates.append((alert_score(info), text[:180], sorted(alert_modes(info)), alert_blob(info), sorted(alert_line_tokens(info)), sorted(alert_line_ids(info))))
    alerts = [
        {"text": text, "modes": modes, "blob": blob, "lines": lines, "lineIds": line_ids}
        for _, text, modes, blob, lines, line_ids in sorted(candidates, key=lambda item: item[0])
    ]
    return alerts[:20]


def alert_title(info):
    text = info.get("subtitle") or info.get("title") or info.get("message") or info.get("description") or ""
    if isinstance(text, dict):
        text = text.get("text") or ""
    for link in info.get("infoLinks") or []:
        text = text or link.get("subtitle") or link.get("urlText") or link.get("smsText") or ""
    return clean_alert_text(text)


def clean_alert_text(text):
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return " ".join(text.split())


def is_relevant_alert(info):
    title = alert_title(info).lower()
    ignored_terms = ("opal sales", "top up", "ticket machines")
    if any(term in title for term in ignored_terms):
        return False
    return bool(alert_modes(info))


def alert_score(info):
    modes = alert_modes(info)
    if "metro" in modes:
        return 0
    if "train" in modes:
        return 1
    if "light_rail" in modes:
        return 2
    return 3


def alert_modes(info):
    modes = set()
    affected = info.get("affected") or {}
    blob = alert_blob(info)
    affected_stop_ids = {
        str(stop.get("id") or stop.get("parent", {}).get("id") or "")
        for stop in affected.get("stops") or []
        if isinstance(stop, dict)
    }
    touches_central = bool(CENTRAL_STOP_IDS & affected_stop_ids) or "central" in blob
    for line in affected.get("lines") or []:
        line_text = " ".join(str(line.get(key) or "") for key in ("name", "number", "description")).upper()
        for mode in WATCHED_LINES:
            if not line_matches_watched(line_text, mode):
                continue
            if mode == "metro":
                if "metro" in blob:
                    modes.add(mode)
            elif touches_central:
                modes.add(mode)
        if touches_central and any(line in line_text for line in TRAIN_ALERT_LINES):
            modes.add("train")
    return modes


def alert_line_tokens(info):
    tokens = set()
    blob = alert_blob(info).upper()
    for token in TRAIN_ALERT_LINES + WATCHED_LINES.get("metro", ()) + WATCHED_LINES.get("light_rail", ()):
        if token and token in blob:
            tokens.add(token)
    return tokens


def alert_line_ids(info):
    ids = set()
    affected = info.get("affected") or {}
    for line in affected.get("lines") or []:
        if isinstance(line, dict):
            line_id = str(line.get("id") or "")
            if line_id:
                ids.add(line_id)
    return ids


def alert_blob(info):
    haystack = [alert_title(info)]
    for link in info.get("infoLinks") or []:
        haystack.extend(str(link.get(key) or "") for key in ("subtitle", "urlText", "smsText", "content"))
    affected = info.get("affected") or {}
    for line in affected.get("lines") or []:
        haystack.extend(str(line.get(key) or "") for key in ("name", "number", "description"))
        operator = line.get("operator") or {}
        haystack.append(str(operator.get("name") or ""))
    for stop in affected.get("stops") or []:
        if isinstance(stop, dict):
            haystack.extend(str(stop.get(key) or "") for key in ("id", "name", "title"))
    return " ".join(haystack).lower()


def load_transport():
    errors = []
    stops = []
    for stop in STOPS:
        try:
            rows = cached(departure_cache_key(stop), DEPARTURE_CACHE_SECONDS, lambda s=stop: load_departures(s))
            stops.append(stop_payload(stop, rows))
        except Exception as exc:
            stops.append(stop_error_payload(stop, exc))
            errors.append(f"{stop['name']}: {exc}")
    try:
        alerts = cached("alerts", ALERT_CACHE_SECONDS, load_alerts)
    except Exception as exc:
        alerts = []
        errors.append(f"alerts: {exc}")
    apply_alerts_to_stops(stops, alerts)
    return {"stops": stops, "errors": errors}


def departure_cache_key(stop):
    direction_ids = ",".join(str(direction.get("stopId") or "") for direction in stop.get("directions", ()))
    return f"departures:{stop.get('mode', '')}:{stop.get('id', '')}:{direction_ids}"


def stop_payload(stop, rows):
    if stop.get("mode") == "train_platforms":
        return {**stop, "platforms": rows, "departures": [], "error": None}
    if stop.get("directions"):
        return {
            "name": stop.get("name"),
            "kind": stop.get("kind"),
            "mode": stop.get("mode"),
            "directions": rows,
            "error": None,
        }
    return {**stop, "departures": rows, "error": None}


def stop_error_payload(stop, exc):
    if stop.get("mode") == "train_platforms":
        empty = {"platforms": [], "departures": []}
    elif stop.get("directions"):
        empty = {"directions": empty_direction_payloads(stop)}
    else:
        empty = {"departures": []}
    return {**public_stop_fields(stop), **empty, "error": str(exc)}


def public_stop_fields(stop):
    return {
        "name": stop.get("name"),
        "kind": stop.get("kind"),
        "mode": stop.get("mode"),
    }


def empty_direction_payloads(stop):
    return [
        {
            "id": direction.get("id"),
            "title": direction.get("title"),
            "departures": [],
        }
        for direction in stop.get("directions", [])
    ]


def apply_alerts_to_stops(stops, alerts):
    for stop in stops:
        mode_alerts = [alert for alert in alerts if stop.get("mode") in alert.get("modes", [])]
        if stop.get("mode") in ("metro", "light_rail"):
            service_mode_alerts = [
                alert for alert in mode_alerts
                if is_service_alert_for_empty_platform(alert)
            ]
            stop["modeAlerts"] = [
                {"text": alert.get("text", "")}
                for alert in service_mode_alerts
            ]
            apply_direction_alerts(stop, service_mode_alerts)
        if stop.get("mode") in ("metro", "light_rail") and not stop_has_departures(stop) and stop.get("modeAlerts"):
            stop["status"] = preferred_mode_alert([alert["text"] for alert in stop["modeAlerts"]], stop.get("mode"))
        if stop.get("mode") == "train_platforms":
            stop["alerts"] = train_platform_header_alerts(alerts)
            apply_train_platform_alerts(stop, alerts)


def stop_has_departures(stop):
    if stop.get("directions"):
        return any(direction.get("departures") for direction in stop.get("directions", []))
    return bool(stop.get("departures"))


def apply_direction_alerts(stop, alerts):
    if not stop.get("directions") or not alerts:
        return
    config_by_id = {
        direction.get("id"): direction
        for source_stop in STOPS
        if source_stop.get("mode") == stop.get("mode")
        for direction in source_stop.get("directions", [])
    }
    for direction in stop.get("directions", []):
        if direction.get("departures"):
            continue
        source = config_by_id.get(direction.get("id"), {})
        notice = preferred_direction_alert(alerts, source.get("noticeTerms", ()))
        if notice:
            direction["notice"] = notice


def preferred_direction_alert(alerts, terms):
    normalized_terms = tuple(str(term).lower() for term in terms if term)
    for alert in alerts:
        text = str(alert.get("text") or "").lower()
        if any(term in text for term in normalized_terms):
            return alert.get("text", "")
    return None


def train_platform_header_alerts(alerts):
    result = []
    seen = set()
    for alert in alerts:
        text = str(alert.get("text") or "")
        if not text or text in seen:
            continue
        if "train" not in alert.get("modes", []):
            continue
        if not is_service_alert_for_empty_platform(alert):
            continue
        badges = train_alert_badges(alert)
        if not badges:
            continue
        seen.add(text)
        result.append({"text": text, "badges": badges, "score": train_header_alert_score(text, badges)})
    result.sort(key=lambda item: item["score"])
    return [{"text": item["text"], "badges": item["badges"]} for item in result[:5]]


def train_header_alert_score(text, badges):
    text_lower = str(text or "").lower()
    has_platform = any(str(badge).startswith("P") for badge in badges)
    score = 0 if has_platform else 20
    if text_lower.startswith("station update"):
        score += 30
    if text_lower in ("cancelled", "running late", "not stopping at"):
        score += 10
    if "city circle" in text_lower or "airport" in text_lower or "central" in text_lower:
        score -= 5
    return score


def train_alert_badges(alert):
    alert_text = str(alert.get("text") or "").lower()
    strong = []
    weak_lines = set()
    for platform_id, meta in TRAIN_PLATFORM_META.items():
        line_id_prefixes = tuple(str(line_id) for line_id in meta.get("line_ids", ()))
        alert_line_ids = tuple(str(line_id) for line_id in alert.get("lineIds") or ())
        line_matches = line_id_prefixes and any(
            line_id.startswith(prefix)
            for line_id in alert_line_ids
            for prefix in line_id_prefixes
        )
        if not line_matches:
            continue
        direction_terms = tuple(str(term).lower() for term in meta.get("terms", ())) + (str(meta.get("kind") or "").lower(),)
        if any(term and term in alert_text for term in direction_terms):
            strong.append(platform_alert_badge(meta))
        else:
            weak_lines.update(str(line).upper() for line in meta.get("lines", ()))
    if strong:
        return unique_badges(strong)
    alert_lines = {str(line).upper() for line in alert.get("lines") or ()}
    weak_lines = weak_lines | alert_lines
    platform_lines = {
        str(line).upper()
        for meta in TRAIN_PLATFORM_META.values()
        for line in meta.get("lines", ())
    }
    return sorted(weak_lines & platform_lines)


def platform_alert_badge(meta):
    lines = "/".join(str(line).upper() for line in meta.get("lines", ()))
    return f"P{meta.get('name')} {lines}".strip()


def unique_badges(values):
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def preferred_mode_alert(alerts, mode):
    if mode == "metro":
        for alert in alerts:
            if "metro" in alert.lower() or "m1" in alert.lower():
                return alert
    return alerts[0]


def apply_train_platform_alerts(stop, alerts):
    for platform in stop.get("platforms") or []:
        if platform.get("departures"):
            continue
        alert = preferred_train_platform_alert(platform, alerts)
        if alert:
            platform["status"] = alert["text"]


def preferred_train_platform_alert(platform, alerts):
    platform_id = platform.get("id")
    meta = TRAIN_PLATFORM_META.get(platform_id, {})
    line_id_prefixes = tuple(str(line_id) for line_id in meta.get("line_ids", ()))
    text_terms = tuple(str(term).lower() for term in meta.get("terms", ())) + (str(platform.get("kind") or "").lower(),)

    for alert in alerts:
        if "train" not in alert.get("modes", []):
            continue
        if not is_service_alert_for_empty_platform(alert):
            continue
        alert_text = str(alert.get("text") or "").lower()
        alert_line_ids = tuple(str(line_id) for line_id in alert.get("lineIds") or ())
        line_matches = line_id_prefixes and any(
            line_id.startswith(prefix)
            for line_id in alert_line_ids
            for prefix in line_id_prefixes
        )
        direction_matches = any(term and term in alert_text for term in text_terms)
        if line_matches and direction_matches:
            return alert
    return None


def is_service_alert_for_empty_platform(alert):
    text = str(alert.get("text") or "").lower()
    blob = str(alert.get("blob") or "").lower()
    if text.startswith("station update"):
        return False
    service_terms = (
        "buses replace",
        "do not run",
        "not running",
        "trackwork",
        "closed",
        "cancelled",
        "canceled",
        "delayed",
        "changed",
        "service changes",
    )
    return any(term in text or term in blob for term in service_terms)


def state_payload():
    errors = []
    try:
        weather = cached("weather", WEATHER_CACHE_SECONDS, load_weather)
    except Exception as exc:
        weather = None
        errors.append(f"weather: {exc}")
    transport = load_transport()
    errors.extend(transport.get("errors", []))
    now = now_sydney()
    return {
        "location": "Central",
        "now": now.isoformat(),
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%a %d %b %Y"),
        "weather": weather,
        "transport": transport,
        "errors": errors,
        "refreshSeconds": 60,
    }


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/healthz":
            self.send_response(200)
            self.end_headers()
            return
        self.send_static(path, include_body=False)

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/api/state":
            self.send_json(state_payload())
            return
        if path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok\n")
            return
        self.send_static(path)

    def send_static(self, path, include_body=True):
        file_path = ROOT / ("index.html" if path in ("/", "") else path.lstrip("/"))
        if not file_path.resolve().is_relative_to(ROOT.resolve()) or not file_path.exists():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type_for_path(file_path))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if include_body:
            self.wfile.write(file_path.read_bytes())

    def send_json(self, value, status=200):
        body = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        return


def content_type_for_path(file_path):
    content_types = {
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".ttf": "font/ttf",
        ".svg": "image/svg+xml",
    }
    return content_types.get(file_path.suffix, "text/html; charset=utf-8")


def main():
    port = int(os.getenv("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"mireader dashboard listening on :{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
