# entity_resolution.py

import uuid
import os
import time
from collections import defaultdict
from math import radians, sin, cos, sqrt, atan2
import requests as _requests
import json

# ------------------------------------------------
# DYNAMIC COORDINATE RESOLVER  (API-only, no hardcoded landmarks)
# ------------------------------------------------

# In-memory cache (populated from disk/Redis on first use)
_GEO_CACHE = {}
_GEO_CACHE_LOADED = False

# Persistent cache files
_CACHE_FILE_DIR = os.path.dirname(os.path.abspath(__file__))
_CACHE_FILES = [
    os.path.join(_CACHE_FILE_DIR, "geo_cache.json"),
    os.path.join(_CACHE_FILE_DIR, "output", "geo_cache.json")
]

# Nominatim requires ≤1 request/second
_last_request_time = 0.0
_redis_client = None

def _get_redis_client():
    global _redis_client
    if _redis_client is None:
        try:
            # Ensure backend is in python path
            import sys
            from pathlib import Path
            backend_path = str(Path(__file__).parent.parent)
            if backend_path not in sys.path:
                sys.path.insert(0, backend_path)
            from db.redis_client import RedisClient
            _redis_client = RedisClient()
        except Exception as e:
            print(f"[Redis] Error initializing in entity_resolution: {e}")
            _redis_client = False
    return _redis_client

def _load_geo_cache():
    """Load the persistent geo-cache from disk into memory (once)."""
    global _GEO_CACHE, _GEO_CACHE_LOADED
    if _GEO_CACHE_LOADED:
        return
    
    # Try local files
    for cache_path in _CACHE_FILES:
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                # Keys are stored as "lat,lon" strings in JSON
                for k, v in raw.items():
                    parts = k.split(",")
                    _GEO_CACHE[(float(parts[0]), float(parts[1]))] = v
                print(f"[Geo Cache] Loaded {len(raw)} entries from {os.path.basename(cache_path)}")
                break # Stop at first found cache file
            except Exception:
                pass
                
    _GEO_CACHE_LOADED = True


def _save_geo_cache():
    """Persist the in-memory geo-cache to disk."""
    try:
        serialisable = {
            f"{lat},{lon}": name
            for (lat, lon), name in _GEO_CACHE.items()
        }
        # Save to both locations to ensure consistency
        for cache_path in _CACHE_FILES:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(serialisable, f, indent=2, ensure_ascii=False)
    except Exception:
        pass


def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000  # Earth radius in meters
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2)**2 + cos(phi1) * cos(phi2) * sin(dlambda / 2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def resolve_coordinates_dynamically(lat, lon):
    """
    Resolve (lat, lon) → human-readable place name using the
    OpenStreetMap Nominatim reverse-geocoding API.

    Results are cached both in-memory/disk and Upstash Redis
    so the API is only called once per unique coordinate pair.
    """
    global _last_request_time

    _load_geo_cache()
    coord_key = (round(lat, 5), round(lon, 5))

    # 1. Check Upstash Redis cache first
    rc = _get_redis_client()
    if rc and rc.connected:
        try:
            cached_val = rc.get_geo(lat, lon)
            if cached_val:
                # Also sync back to in-memory cache if not present
                if coord_key not in _GEO_CACHE:
                    _GEO_CACHE[coord_key] = cached_val
                return cached_val
        except Exception as e:
            print(f"[Redis] Error getting geo cache: {e}")

    # 2. Check local in-memory cache
    if coord_key in _GEO_CACHE:
        # Sync back to Redis if Redis was missing it
        if rc and rc.connected:
            try:
                rc.set_geo(lat, lon, _GEO_CACHE[coord_key])
            except Exception:
                pass
        return _GEO_CACHE[coord_key]

    # 3. Call Nominatim reverse-geocoding API
    try:
        # Rate-limit: wait if last request was < 1 s ago
        elapsed = time.time() - _last_request_time
        if elapsed < 1.0:
            time.sleep(1.0 - elapsed)

        resp = _requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "lat": lat,
                "lon": lon,
                "format": "json",
                "zoom": 18,
                "addressdetails": 1,
            },
            headers={
                "User-Agent": "TATHYA-DF/1.0 (academic research project)"
            },
            timeout=5,
        )
        _last_request_time = time.time()
        resp.raise_for_status()
        data = resp.json()

        address = data.get("address", {})
        road    = address.get("road")
        suburb  = address.get("suburb") or address.get("neighbourhood")
        city    = (address.get("city")
                   or address.get("town")
                   or address.get("county"))

        parts = [p for p in [road, suburb, city] if p]
        if parts:
            resolved_str = ", ".join(parts).lower()
            # Cache locally
            _GEO_CACHE[coord_key] = resolved_str
            _save_geo_cache()
            # Cache in Redis
            if rc and rc.connected:
                try:
                    rc.set_geo(lat, lon, resolved_str)
                except Exception:
                    pass
            return resolved_str

        # If address parts are empty but display_name exists
        display = data.get("display_name")
        if display:
            # Take the first 3 comma-separated parts for brevity
            short = ", ".join(display.split(",")[:3]).strip().lower()
            _GEO_CACHE[coord_key] = short
            _save_geo_cache()
            if rc and rc.connected:
                try:
                    rc.set_geo(lat, lon, short)
                except Exception:
                    pass
            return short
    except Exception:
        pass

    # 4. Fallback to clean coordinate label
    fallback_str = f"location near {lat:.4f}n, {lon:.4f}e"
    _GEO_CACHE[coord_key] = fallback_str
    _save_geo_cache()
    if rc and rc.connected:
        try:
            rc.set_geo(lat, lon, fallback_str)
        except Exception:
            pass
    return fallback_str


# ------------------------------------------------
# HELPERS
# ------------------------------------------------

def generate_master_id():

    return f"MASTER_{uuid.uuid4().hex[:8]}"


# ------------------------------------------------
# EXTRACT ENTITY VALUE
# ------------------------------------------------

def extract_entity_value(entity):

    entity_type = entity.get("type")

    attributes = entity.get(
        "attributes",
        {}
    )

    # ------------------------------------------------
    # PERSON
    # ------------------------------------------------

    if entity_type == "PERSON":

        return (
            attributes.get("name", "")
            .lower()
            .strip()
        )

    # ------------------------------------------------
    # PHONE
    # ------------------------------------------------

    elif entity_type == "PHONE_NUMBER":

        return (
            str(
                attributes.get("number")
                or attributes.get("identifier")
            )
            .replace(".0", "")
            .strip()
        )

    # ------------------------------------------------
    # EMAIL
    # ------------------------------------------------

    elif entity_type == "EMAIL":

        return (
            attributes.get("email", "")
            .lower()
            .strip()
        )

    # ------------------------------------------------
    # ACCOUNT
    # ------------------------------------------------

    elif entity_type == "ACCOUNT":

        # support both old schema (id) and new schema (attributes.account_id)
        return (
            str(
                attributes.get("account_id")
                or entity.get("id")
                or ""
            )
            .lower()
            .strip()
        )

    # ------------------------------------------------
    # DEVICES
    # ------------------------------------------------

    elif entity_type in [
        "DEVICE",
        "VEHICLE",
        "TRACKER",
        "WEARABLE_DEVICE"
    ]:

        return (
            attributes.get("identifier", "")
            .lower()
            .strip()
        )

    # ------------------------------------------------
    # LOCATION
    # ------------------------------------------------

    elif entity_type == "LOCATION":

        name = attributes.get("name")

        if name:

            return (
                name
                .lower()
                .strip()
            )

        lat = attributes.get("latitude")

        lon = attributes.get("longitude")

        if lat is not None and lon is not None:
            try:
                # Use a deterministic coordinate key during entity resolution.
                # Display-name reverse geocoding is optional enrichment and must
                # not make core evidence processing depend on network access.
                return f"{float(lat):.5f},{float(lon):.5f}"
            except (TypeError, ValueError):
                return f"{lat},{lon}"

    # ------------------------------------------------
    # CELL TOWER
    # ------------------------------------------------

    elif entity_type == "CELL_TOWER":
        tower_id = attributes.get("tower_id") or entity.get("temp_id") or entity.get("id") or "unknown"
        return f"cell tower ({tower_id})".lower()

    # ------------------------------------------------
    # CAMERA
    # ------------------------------------------------

    elif entity_type == "CAMERA":
        loc = attributes.get("location")
        cam_id = entity.get("temp_id") or entity.get("id") or "unknown"
        if loc:
            loc_str = str(loc).replace("_", " ").title()
            return f"cctv camera at {loc_str}".lower()
        else:
            return f"cctv camera ({cam_id})".lower()

    # ------------------------------------------------
    # PLATFORM
    # ------------------------------------------------

    elif entity_type == "PLATFORM":

        return (
            attributes.get("name", "")
            .lower()
            .strip()
        )

    # ------------------------------------------------
    # SOCIAL HANDLE
    # ------------------------------------------------

    elif entity_type == "SOCIAL_HANDLE":

        return (
            attributes.get("handle", "")
            .lower()
            .strip()
        )

    # ------------------------------------------------
    # UNIVERSAL FALLBACK
    # Any entity type not listed above still gets a
    # unique value so it ends up in resolved_mapping.
    # ------------------------------------------------

    fallback = entity.get("temp_id") or entity.get("id")

    if fallback:
        return str(fallback).lower().strip()

    return None


# ------------------------------------------------
# MERGE CLUSTERS
# ------------------------------------------------

def merge_clusters(
    cluster_a,
    cluster_b,
    clusters
):

    if cluster_a == cluster_b:
        return

    for entity_id in clusters[cluster_b]:

        clusters[cluster_a].add(entity_id)

    del clusters[cluster_b]


# ------------------------------------------------
# FUZZY NAME MERGE FOR PERSONS
# ------------------------------------------------

def fuzzy_merge_persons(clusters, entity_lookup, entity_to_cluster):

    """
    Merge PERSON clusters where one name is a substring of the other.
    Example: "rahul" and "rahul sen" → merged into one cluster.
    """

    # Collect one (cluster_id, name) per cluster that has a PERSON
    person_clusters = []

    for cluster_id, entity_ids in list(clusters.items()):

        for eid in entity_ids:

            entity = entity_lookup.get(eid)

            if entity and entity.get("type") == "PERSON":

                name = (
                    entity.get("attributes", {})
                    .get("name", "")
                    .lower()
                    .strip()
                )

                if name:
                    person_clusters.append((cluster_id, name))
                    break

    # Compare all pairs — merge if one name is a substring of the other
    merged = set()

    for i, (cid_a, name_a) in enumerate(person_clusters):

        if cid_a in merged or cid_a not in clusters:
            continue

        for j, (cid_b, name_b) in enumerate(person_clusters):

            if i >= j:
                continue

            if cid_b in merged or cid_b not in clusters:
                continue

            if cid_a == cid_b:
                continue

            # substring match: "rahul" in "rahul sen" or vice versa
            if name_a in name_b or name_b in name_a:

                merge_clusters(cid_a, cid_b, clusters)
                merged.add(cid_b)

                for eid in clusters[cid_a]:
                    entity_to_cluster[eid] = cid_a


# ------------------------------------------------
# ENTITY RESOLUTION
# ------------------------------------------------

def resolve_entities(entities, relations):
    """Resolve duplicate records only within the same entity type.

    Relationships such as USES_PHONE / OWNS_ACCOUNT / USES_DEVICE describe
    associations; they are never identity evidence and must never merge nodes.
    Fuzzy person-name matches are deliberately left separate for review.
    """
    entity_lookup = {}
    groups = defaultdict(list)
    resolved_mapping = {}
    master_entities = []

    for index, entity in enumerate(entities or []):
        entity_id = entity.get("temp_id") or entity.get("id")
        if not entity_id:
            # Keep malformed records distinct rather than accidentally merging them.
            entity_id = f"UNIDENTIFIED_ENTITY_{index + 1}"
        entity_id = str(entity_id)
        entity_lookup[entity_id] = entity
        entity_type = str(entity.get("type") or "UNKNOWN").upper()
        # Never call network geocoding as part of identity resolution.
        if entity_type == "LOCATION":
            attrs = entity.get("attributes", {}) or {}
            name = attrs.get("name")
            lat, lon = attrs.get("latitude"), attrs.get("longitude")
            if name:
                value = str(name).strip().casefold()
            elif lat is not None and lon is not None:
                value = f"{float(lat):.6f},{float(lon):.6f}"
            else:
                value = None
        else:
            value = extract_entity_value(entity)
        normalized = str(value).strip().casefold() if value is not None else ""
        # Type is part of the identity key. A phone can never merge with a person.
        if normalized:
            groups[(entity_type, normalized)].append(entity_id)
        else:
            groups[(entity_type, f"__unique__:{entity_id}")].append(entity_id)

    def classify_master_type(entity_type):
        mapping = {
            "PERSON": "PERSON", "PHONE_NUMBER": "PHONE_NUMBER",
            "EMAIL": "EMAIL", "ACCOUNT": "ACCOUNT",
            "DEVICE": "DEVICE", "VEHICLE": "VEHICLE",
            "TRACKER": "DEVICE", "WEARABLE_DEVICE": "DEVICE",
            "LOCATION": "PLACE", "CELL_TOWER": "INFRASTRUCTURE",
            "CAMERA": "INFRASTRUCTURE", "PLATFORM": "PLATFORM",
            "SOCIAL_HANDLE": "SOCIAL_HANDLE",
        }
        return mapping.get(entity_type, entity_type or "ENTITY")

    for (entity_type, normalized_value), entity_ids in groups.items():
        master_id = generate_master_id()
        for entity_id in entity_ids:
            resolved_mapping[entity_id] = master_id
        originals = [entity_lookup[eid] for eid in entity_ids if eid in entity_lookup]
        values = []
        for original in originals:
            val = extract_entity_value(original)
            if val not in (None, ""):
                values.append(str(val))
        master_entities.append({
            "master_id": master_id,
            "master_type": classify_master_type(entity_type),
            "entity_types": [entity_type],
            "resolved_values": list(dict.fromkeys(values)),
            "source_entities": list(entity_ids),
            "resolution_method": "exact_same_type" if not normalized_value.startswith("__unique__:") else "unresolved_singleton",
            "review_required": entity_type == "PERSON" and len(entity_ids) > 1,
        })

    # Relationship endpoints without entity definitions remain separate unknown nodes.
    for relation in relations or []:
        for endpoint in (relation.get("source"), relation.get("target")):
            if endpoint is None:
                continue
            endpoint = str(endpoint)
            if endpoint not in resolved_mapping:
                master_id = generate_master_id()
                resolved_mapping[endpoint] = master_id
                master_entities.append({
                    "master_id": master_id,
                    "master_type": "UNKNOWN",
                    "entity_types": ["UNKNOWN"],
                    "resolved_values": [endpoint],
                    "source_entities": [endpoint],
                    "resolution_method": "unresolved_endpoint",
                    "review_required": True,
                })

    return {"resolved_mapping": resolved_mapping, "master_entities": master_entities}

