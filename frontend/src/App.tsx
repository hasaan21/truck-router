import { useEffect, useRef, useState, type FormEvent } from "react"
import { planTrip } from "./api"
import { ForecastSlider } from "./components/ForecastSlider"
import { MapView } from "./components/MapView"
import { RouteForm } from "./components/RouteForm"
import { RouteList } from "./components/RouteList"
import { defaultDepartureLocal, localTimeZone } from "./format"
import type { Place, PlanResponse } from "./types"

export default function App() {
  const [origin, setOrigin] = useState<Place | null>(null)
  const [destination, setDestination] = useState<Place | null>(null)
  const [departure, setDeparture] = useState(defaultDepartureLocal)
  const [load, setLoad] = useState("35000")
  const [interval, setIntervalMiles] = useState(25)
  const [plan, setPlan] = useState<PlanResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stepOnly, setStepOnly] = useState(false)
  const resultsRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)")
    const apply = () => setStepOnly(media.matches)
    apply()
    media.addEventListener("change", apply)
    return () => media.removeEventListener("change", apply)
  }, [])

  useEffect(() => {
    if (!playing || stepOnly) {
      return
    }
    const timer = window.setInterval(() => {
      setHour((current) => (current + 1) % 48)
    }, 800)
    return () => window.clearInterval(timer)
  }, [playing, stepOnly])

  useEffect(() => {
    if (plan) {
      resultsRef.current?.scrollIntoView({ block: "nearest" })
    }
  }, [plan])

  async function onSubmit(event: FormEvent) {
    event.preventDefault()
    if (!origin || !destination) {
      setError("Choose an origin and destination from the suggestions.")
      return
    }
    const weight = Number(load)
    if (!Number.isFinite(weight) || weight < 0) {
      setError("Enter a load weight in pounds.")
      return
    }
    setLoading(true)
    setError(null)
    setPlaying(false)
    try {
      const next = await planTrip({
        origin,
        destination,
        departure,
        timezone: localTimeZone(),
        load_weight_lb: weight,
        sample_interval_miles: interval,
      })
      setPlan(next)
      setSelectedId(next.recommended_route_id)
      setHour(0)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not plan that trip.")
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="shell">
      <aside className="panel">
        <div className="panel-body">
          <header className="mast">
            <p className="kicker">Truck router</p>
            <h1>Weather desk</h1>
            <p>
              Compare three routes by the weather the truck will meet, then by how long the drive takes.
            </p>
          </header>
          <RouteForm
            origin={origin}
            destination={destination}
            departure={departure}
            load={load}
            interval={interval}
            loading={loading}
            onOrigin={setOrigin}
            onDestination={setDestination}
            onDeparture={setDeparture}
            onLoad={setLoad}
            onInterval={setIntervalMiles}
            onSubmit={onSubmit}
          />
          {error ? (
            <p className="banner" role="alert">
              {error}
            </p>
          ) : null}
          <div className="results-scroll" ref={resultsRef}>
            {plan ? (
              <RouteList plan={plan} selectedId={selectedId} onSelect={setSelectedId} />
            ) : (
              <p className="empty">
                Pick both ends of the trip. Checkpoints are scored for wind, rain, and snow at the estimated arrival, including the load limits.
              </p>
            )}
          </div>
        </div>
        {plan ? (
          <ForecastSlider
            originTime={plan.heatmap.origin_time}
            hour={hour}
            playing={playing}
            stepOnly={stepOnly}
            onHour={(next) => {
              setPlaying(false)
              setHour(next)
            }}
            onToggle={() => {
              if (stepOnly) {
                setHour((current) => (current + 1) % 48)
                return
              }
              setPlaying((current) => !current)
            }}
          />
        ) : null}
        <p className="credits">
          Routes by OpenRouteService. Weather by Open-Meteo. Map data © OpenStreetMap.
        </p>
      </aside>
      <MapView plan={plan} selectedId={selectedId} hour={hour} loading={loading} onSelect={setSelectedId} />
    </main>
  )
}
