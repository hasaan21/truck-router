# Weather-Aware Truck Router

A React and Django app that compares up to three truck routes and recommends the one that best balances weather risk and travel time.

The driver enters an origin, a destination, a departure time, and a load weight. The API asks OpenRouteService for truck routes, samples weather along each one, and ranks the results. The map draws every route, its checkpoints, and a corridor forecast that can be stepped from departure through the next 48 hours.

## Run locally

Backend, from `backend/`:

```bash
poetry install
poetry run python manage.py runserver
```

Frontend, from `frontend/`:

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The Vite dev server proxies `/api` to Django on port 8000.

## Configuration

Copy `.env.example` to `.env` in the repository root (or to `backend/.env`).

Routing and geocoding use the free HeiGIT OpenRouteService endpoint:

```bash
OPENROUTESERVICE_BASE_URL=https://api.heigit.org
OPENROUTESERVICE_API_KEY=
```

Create a free Standard key at [account.heigit.org](https://account.heigit.org/info/plans). The key stays on the server. Weather comes from [Open-Meteo](https://open-meteo.com/) and does not need a key. The map uses the free [OpenFreeMap](https://openfreemap.org/) Liberty style.

Directions prefer the `driving-hgv` profile and ask for two alternatives besides the primary route. If that profile returns fewer than three distinct routes, the API uses `driving-car` when it produces more options.

## Risk rules

Each checkpoint takes the worst of wind, rain, and snow.

| Hazard | Low | Moderate | High | Severe | No travel |
| --- | --- | --- | --- | --- | --- |
| Wind | < 25 mph | 25–34 | 35–44 | 45–54 | ≥ 55 mph |
| Rain | < 0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow | < 0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Where two bands meet, the higher one is used. Load weight then adjusts wind:

- 55 mph or more is no travel for any load
- 45–54 mph and a load over 30,000 lb is no travel
- 35–44 mph and a load over 40,000 lb is severe

Checkpoints are placed every 10, 25, or 50 miles, including the destination. A checkpoint owns the miles until the next one. Arrival time follows distance along the route and the route duration. Wind is Open-Meteo `wind_speed_10m`. Rain is `rain` plus `showers`. Snow is `snowfall`.

Routes are ordered by fewest no-travel miles, then fewest severe miles, then fewest high miles, then lowest mile-weighted average risk (`low` = 0 through `no travel` = 4), then shortest duration. No-travel miles rank first because that outcome is stricter than severe. The forecast must cover the departure, the arrivals, and 48 hours after departure, so the departure needs to sit inside Open-Meteo's 7-day window with room for that slider.

## API

`GET /api/geocode/?q=chicago` returns `{label, lat, lon}` suggestions.

`POST /api/plan/` accepts:

```json
{
  "origin": {"label": "Chicago, Illinois, USA", "lat": 41.88, "lon": -87.63},
  "destination": {"label": "Denver, Colorado, USA", "lat": 39.74, "lon": -104.99},
  "departure": "2026-10-18T08:00:00",
  "timezone": "America/Chicago",
  "load_weight_lb": 35000,
  "sample_interval_miles": 25
}
```

The response includes the recommended route, GeoJSON for each option, checkpoint weather and risk, mile totals, and heatmap points with 48 hourly risk scores. The slider only switches which of those scores is drawn.

## Tests

From `backend/`:

```bash
poetry run pytest
```

## Credits

Road geometry and geocoding are provided by [OpenRouteService](https://openrouteservice.org/) / HeiGIT, using OpenStreetMap data. Weather is from [Open-Meteo](https://open-meteo.com/), licensed CC BY 4.0. Map tiles are from [OpenFreeMap](https://openfreemap.org/), also based on OpenStreetMap.
