import type { FormEvent } from "react"
import type { Place } from "../types"
import { PlaceField } from "./PlaceField"

interface RouteFormProps {
  origin: Place | null
  destination: Place | null
  departure: string
  load: string
  interval: number
  loading: boolean
  onOrigin: (place: Place | null) => void
  onDestination: (place: Place | null) => void
  onDeparture: (value: string) => void
  onLoad: (value: string) => void
  onInterval: (value: number) => void
  onSubmit: (event: FormEvent) => void
}

export function RouteForm({
  origin,
  destination,
  departure,
  load,
  interval,
  loading,
  onOrigin,
  onDestination,
  onDeparture,
  onLoad,
  onInterval,
  onSubmit,
}: RouteFormProps) {
  return (
    <form className="trip-form" onSubmit={onSubmit}>
      <PlaceField label="Origin" value={origin} onChange={onOrigin} />
      <PlaceField label="Destination" value={destination} onChange={onDestination} />
      <label className="field">
        <span>Departure</span>
        <input
          type="datetime-local"
          value={departure}
          onChange={(event) => onDeparture(event.target.value)}
          required
        />
      </label>
      <div className="split">
        <label className="field">
          <span>Load weight</span>
          <input
            type="number"
            min={0}
            max={200000}
            step={500}
            value={load}
            onChange={(event) => onLoad(event.target.value)}
            required
          />
          <small>pounds</small>
        </label>
        <label className="field">
          <span>Sample every</span>
          <select
            value={interval}
            onChange={(event) => onInterval(Number(event.target.value))}
          >
            <option value={10}>10 miles</option>
            <option value={25}>25 miles</option>
            <option value={50}>50 miles</option>
          </select>
        </label>
      </div>
      <button className="primary" type="submit" disabled={loading}>
        {loading ? "Planning routes…" : "Plan routes"}
      </button>
    </form>
  )
}
