"""Default service addresses and values that are not deployment secrets.

Base URLs can be overridden with environment variables. Path segments stay
here because they belong to each provider's API.
"""

HEIGIT_ACCOUNT_URL = "https://account.heigit.org"
OPENROUTESERVICE_BASE_URL = "https://api.heigit.org"
OPEN_METEO_BASE_URL = "https://api.open-meteo.com"
OPEN_METEO_GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
OSRM_BASE_URL = "https://router.project-osrm.org"

ORS_AUTOCOMPLETE_PATH = "/pelias/v1/autocomplete"
ORS_DIRECTIONS_PATH = "/openrouteservice/v2/directions/{profile}/geojson"
OSRM_DRIVING_PATH = "/route/v1/driving/{path}"
OPEN_METEO_FORECAST_PATH = "/v1/forecast"

METERS_PER_MILE = 1609.344
ORS_FREE_TIER_MAX_METERS = 100_000
MILES_PER_DEGREE = 69.172
FORECAST_DAYS = 7
FORECAST_HOURS = 48
WEATHER_BATCH = 50
SAMPLE_INTERVALS = {10, 25, 50}
VIA_OFFSETS_MILES = (12.0, 22.0, 35.0)
