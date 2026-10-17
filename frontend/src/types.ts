export type RiskName = "low" | "moderate" | "high" | "severe" | "no_travel"

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface Checkpoint {
  lat: number
  lon: number
  mile: number
  eta: string
  wind_mph: number
  rain_in_hr: number
  snow_in_hr: number
  wind_risk: RiskName
  rain_risk: RiskName
  snow_risk: RiskName
  risk: RiskName
  segment_miles: number
}

export interface RouteSummary {
  distance_miles: number
  duration_seconds: number
  no_travel_miles: number
  severe_miles: number
  high_miles: number
  moderate_miles: number
  low_miles: number
  average_risk: number
}

export interface PlannedRoute {
  id: string
  profile: string
  summary: RouteSummary
  geometry: { type: "LineString"; coordinates: [number, number][] }
  checkpoints: Checkpoint[]
}

export interface HeatPoint {
  lat: number
  lon: number
  risks: number[]
}

export interface PlanResponse {
  recommended_route_id: string | null
  profile: string
  departure: string
  timezone: string
  load_weight_lb: number
  sample_interval_miles: number
  origin: Place
  destination: Place
  routes: PlannedRoute[]
  heatmap: {
    hours: number
    origin_time: string
    points: HeatPoint[]
  }
}

export interface PlanRequest {
  origin: Place
  destination: Place
  departure: string
  timezone: string
  load_weight_lb: number
  sample_interval_miles: number
}
