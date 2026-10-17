import { averageRiskLabel, RISK_LABELS, ROUTE_COLORS } from "../risk"
import type { PlanResponse, PlannedRoute } from "../types"
import { formatDuration, formatMiles } from "../format"

interface RouteListProps {
  plan: PlanResponse
  selectedId: string | null
  onSelect: (routeId: string) => void
}

const LETTERS = ["A", "B", "C"]

export function RouteList({ plan, selectedId, onSelect }: RouteListProps) {
  return (
    <section className="results">
      <div className="results-head">
        <h2>Route options</h2>
        <p>
          {plan.origin.label} to {plan.destination.label}
        </p>
      </div>
      {plan.profile === "driving-car" ? (
        <p className="note">
          Truck restrictions did not yield three distinct routes, so these options use the car network.
        </p>
      ) : null}
      {plan.profile === "osrm" ? (
        <p className="note">
          OpenRouteService refused this API key, so these options use the public driving network.
        </p>
      ) : null}
      {plan.profile === "osrm-limit" ? (
        <p className="note">
          This trip is longer than the free OpenRouteService limit, so these options use the public driving network.
        </p>
      ) : null}
      <ol className="route-list">
        {plan.routes.map((route, index) => (
          <li key={route.id}>
            <RouteCard
              route={route}
              letter={LETTERS[index] ?? String(index + 1)}
              color={ROUTE_COLORS[index] ?? ROUTE_COLORS[0]}
              recommended={route.id === plan.recommended_route_id}
              selected={route.id === selectedId}
              onSelect={onSelect}
            />
          </li>
        ))}
      </ol>
    </section>
  )
}

function RouteCard({
  route,
  letter,
  color,
  recommended,
  selected,
  onSelect,
}: {
  route: PlannedRoute
  letter: string
  color: string
  recommended: boolean
  selected: boolean
  onSelect: (routeId: string) => void
}) {
  const summary = route.summary
  const average = averageRiskLabel(summary.average_risk)
  return (
    <button
      type="button"
      className={selected ? "route-card selected" : "route-card"}
      onClick={() => onSelect(route.id)}
    >
      <div className="route-title">
        <span className="route-letter" style={{ background: color }}>
          {letter}
        </span>
        <strong>{formatMiles(summary.distance_miles)}</strong>
        <span>{formatDuration(summary.duration_seconds)}</span>
        {recommended ? <em>Recommended</em> : null}
      </div>
      <p className={`average risk-${average}`}>
        Average risk {summary.average_risk.toFixed(2)} · {RISK_LABELS[average]}
      </p>
      <dl className="mile-row">
        <div>
          <dt>No travel</dt>
          <dd>{formatMiles(summary.no_travel_miles)}</dd>
        </div>
        <div>
          <dt>Severe</dt>
          <dd>{formatMiles(summary.severe_miles)}</dd>
        </div>
        <div>
          <dt>High</dt>
          <dd>{formatMiles(summary.high_miles)}</dd>
        </div>
      </dl>
    </button>
  )
}
