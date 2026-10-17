import {
  GeoJSONSource,
  LngLatBounds,
  Map,
  NavigationControl,
  Popup,
  type ExpressionSpecification,
} from "maplibre-gl"
import { useEffect, useRef } from "react"
import "maplibre-gl/dist/maplibre-gl.css"
import { riskSegments } from "../geo"
import { RISK_COLORS, RISK_LABELS, ROUTE_COLORS, SCORE_TO_RISK } from "../risk"
import type { Checkpoint, HeatPoint, PlanResponse, RiskName } from "../types"
import { formatWhen } from "../format"

const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty"
const EMPTY = { type: "FeatureCollection" as const, features: [] }

interface MapViewProps {
  plan: PlanResponse | null
  selectedId: string | null
  hour: number
  onSelect: (routeId: string) => void
}

export function MapView({ plan, selectedId, hour, onSelect }: MapViewProps) {
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<Map | null>(null)
  const popupRef = useRef<Popup | null>(null)
  const planRef = useRef(plan)
  const onSelectRef = useRef(onSelect)
  const readyRef = useRef(false)
  planRef.current = plan
  onSelectRef.current = onSelect

  useEffect(() => {
    if (!container.current) {
      return
    }
    const map = new Map({
      container: container.current,
      style: MAP_STYLE,
      center: [-98.35, 39.5],
      zoom: 3.5,
    })
    map.addControl(new NavigationControl({ showCompass: false }), "top-right")
    map.on("load", () => {
      map.addSource("heat", { type: "geojson", data: EMPTY })
      map.addSource("casing", { type: "geojson", data: EMPTY })
      map.addSource("routes", { type: "geojson", data: EMPTY })
      map.addSource("checkpoints", { type: "geojson", data: EMPTY })
      map.addLayer({
        id: "heat",
        type: "circle",
        source: "heat",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 12, 7, 22, 11, 40],
          "circle-color": riskPaint(),
          "circle-opacity": 0.62,
          "circle-blur": 0.45,
        },
      })
      map.addLayer({
        id: "casing",
        type: "line",
        source: "casing",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["case", ["==", ["get", "selected"], 1], 9, 5],
          "line-opacity": 0.95,
        },
      })
      map.addLayer({
        id: "routes",
        type: "line",
        source: "routes",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": riskPaint(),
          "line-width": ["case", ["==", ["get", "selected"], 1], 4.5, 2.5],
        },
      })
      map.addLayer({
        id: "checkpoints",
        type: "circle",
        source: "checkpoints",
        paint: {
          "circle-radius": ["case", ["==", ["get", "selected"], 1], 6.5, 4.5],
          "circle-color": riskPaint(),
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.6,
        },
      })
      readyRef.current = true
      map.resize()
      paintRoutes(map, planRef.current, planRef.current?.recommended_route_id ?? null)
      paintHeat(map, planRef.current, 0)
    })
    map.on("click", "checkpoints", (event) => {
      const feature = event.features?.[0]
      const routeId = stringProperty(feature, "routeId")
      const index = Number(stringProperty(feature, "index"))
      const route = planRef.current?.routes.find((item) => item.id === routeId)
      const checkpoint = route?.checkpoints[index]
      if (!route || !checkpoint) {
        return
      }
      popupRef.current?.remove()
      popupRef.current = new Popup({ offset: 16, maxWidth: "280px", className: "risk-popup" })
        .setLngLat(event.lngLat)
        .setDOMContent(popupNode(checkpoint))
        .addTo(map)
      onSelectRef.current(route.id)
    })
    map.on("mouseenter", "checkpoints", () => {
      map.getCanvas().style.cursor = "pointer"
    })
    map.on("mouseleave", "checkpoints", () => {
      map.getCanvas().style.cursor = ""
    })
    const observer = new ResizeObserver(() => map.resize())
    observer.observe(container.current)
    mapRef.current = map
    return () => {
      observer.disconnect()
      popupRef.current?.remove()
      readyRef.current = false
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) {
      return
    }
    paintRoutes(map, plan, selectedId)
    if (!plan) {
      return
    }
    const bounds = new LngLatBounds()
    for (const route of plan.routes) {
      for (const coordinate of route.geometry.coordinates) {
        bounds.extend(coordinate)
      }
    }
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 56, duration: 800, maxZoom: 8 })
    }
  }, [plan])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) {
      return
    }
    paintRoutes(map, plan, selectedId)
  }, [selectedId, plan])

  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) {
      return
    }
    paintHeat(map, plan, hour)
  }, [plan, hour])

  return (
    <div className="map-wrap">
      <div ref={container} className="map" />
      <ul className="legend">
        {(Object.keys(RISK_COLORS) as RiskName[]).map((risk) => (
          <li key={risk}>
            <i style={{ background: RISK_COLORS[risk] }} />
            {RISK_LABELS[risk]}
          </li>
        ))}
      </ul>
    </div>
  )
}

function paintRoutes(map: Map, plan: PlanResponse | null, selectedId: string | null) {
  const ordered = [...(plan?.routes ?? [])].sort(
    (left, right) => Number(left.id === selectedId) - Number(right.id === selectedId),
  )
  const casing = ordered.map((route, index) => ({
    type: "Feature",
    properties: {
      color: ROUTE_COLORS[plan?.routes.findIndex((item) => item.id === route.id) ?? index] ?? ROUTE_COLORS[0],
      selected: route.id === selectedId ? 1 : 0,
    },
    geometry: route.geometry,
  }))
  const lines: object[] = []
  const checkpoints: object[] = []
  for (const route of ordered) {
    const selected = route.id === selectedId ? 1 : 0
    for (const segment of riskSegments(route)) {
      lines.push({
        type: "Feature",
        properties: { risk: segment.risk, selected },
        geometry: { type: "LineString", coordinates: segment.coordinates },
      })
    }
    route.checkpoints.forEach((checkpoint, index) => {
      checkpoints.push({
        type: "Feature",
        properties: {
          routeId: route.id,
          index,
          risk: checkpoint.risk,
          selected,
        },
        geometry: { type: "Point", coordinates: [checkpoint.lon, checkpoint.lat] },
      })
    })
  }
  setGeoJson(map, "casing", casing)
  setGeoJson(map, "routes", lines)
  setGeoJson(map, "checkpoints", checkpoints)
}

function paintHeat(map: Map, plan: PlanResponse | null, hour: number) {
  const points = plan?.heatmap.points ?? []
  const features = points.map((point) => ({
    type: "Feature",
    properties: { risk: scoreRisk(point, hour) },
    geometry: { type: "Point", coordinates: [point.lon, point.lat] },
  }))
  setGeoJson(map, "heat", features)
}

function setGeoJson(map: Map, id: string, features: object[]) {
  const source = map.getSource(id) as GeoJSONSource | undefined
  void source?.setData({
    type: "FeatureCollection",
    features,
  } as Parameters<GeoJSONSource["setData"]>[0])
}

function scoreRisk(point: HeatPoint, hour: number): RiskName {
  return SCORE_TO_RISK[point.risks[hour] ?? 0] ?? "low"
}

function riskPaint(): ExpressionSpecification {
  return [
    "match",
    ["get", "risk"],
    "low",
    RISK_COLORS.low,
    "moderate",
    RISK_COLORS.moderate,
    "high",
    RISK_COLORS.high,
    "severe",
    RISK_COLORS.severe,
    "no_travel",
    RISK_COLORS.no_travel,
    "#94a3b8",
  ]
}

function stringProperty(feature: { properties?: Record<string, unknown> | null } | undefined, key: string): string {
  const value = feature?.properties?.[key]
  return value == null ? "" : String(value)
}

function popupNode(point: Checkpoint): HTMLElement {
  const root = document.createElement("div")
  root.className = "popup-card"
  const title = document.createElement("p")
  title.className = "popup-title"
  title.textContent = `Mile ${Math.round(point.mile)} · ${formatWhen(point.eta)}`
  const risk = document.createElement("p")
  risk.className = `popup-risk risk-${point.risk}`
  risk.textContent = RISK_LABELS[point.risk]
  const list = document.createElement("ul")
  for (const line of [
    `Wind ${point.wind_mph.toFixed(0)} mph · ${RISK_LABELS[point.wind_risk]}`,
    `Rain ${point.rain_in_hr.toFixed(2)} in/hr · ${RISK_LABELS[point.rain_risk]}`,
    `Snow ${point.snow_in_hr.toFixed(2)} in/hr · ${RISK_LABELS[point.snow_risk]}`,
  ]) {
    const item = document.createElement("li")
    item.textContent = line
    list.append(item)
  }
  root.append(title, risk, list)
  return root
}
