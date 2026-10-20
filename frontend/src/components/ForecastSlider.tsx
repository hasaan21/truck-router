import { addHours, formatWhen } from "../format"
import { RISK_COLORS, RISK_LABELS, SCORE_TO_RISK } from "../risk"
import type { HeatPoint, RiskName } from "../types"

interface ForecastSliderProps {
  originTime: string
  hour: number
  playing: boolean
  stepOnly: boolean
  points: HeatPoint[]
  onHour: (hour: number) => void
  onToggle: () => void
}

export function ForecastSlider({
  originTime,
  hour,
  playing,
  stepOnly,
  points,
  onHour,
  onToggle,
}: ForecastSliderProps) {
  const hours = points[0]?.risks.length ?? 48
  return (
    <div className="slider">
      <div className="slider-top">
        <span>Corridor forecast</span>
        <strong>{formatWhen(addHours(originTime, hour))}</strong>
      </div>
      <div className="hour-strip" aria-hidden="true">
        {Array.from({ length: hours }, (_, index) => (
          <button
            key={index}
            type="button"
            className={index === hour ? "active" : undefined}
            style={{ background: RISK_COLORS[worstRisk(points, index)] }}
            tabIndex={-1}
            onClick={() => onHour(index)}
          />
        ))}
      </div>
      <p className="hour-summary">{describeHour(points, hour)}</p>
      <div className="slider-row">
        <button
          type="button"
          className="ghost"
          aria-pressed={stepOnly ? undefined : playing}
          onClick={onToggle}
        >
          {stepOnly ? "Next hour" : playing ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          min={0}
          max={hours - 1}
          value={hour}
          aria-valuetext={`${hour} hours after departure. ${describeHour(points, hour)}`}
          aria-label="Hours after departure"
          onChange={(event) => onHour(Number(event.target.value))}
        />
        <span className="hour-chip">+{hour}h</span>
      </div>
    </div>
  )
}

function worstRisk(points: HeatPoint[], hour: number): RiskName {
  let score = 0
  for (const point of points) {
    score = Math.max(score, point.risks[hour] ?? 0)
  }
  return SCORE_TO_RISK[score] ?? "low"
}

function describeHour(points: HeatPoint[], hour: number): string {
  if (points.length === 0) {
    return "No corridor samples"
  }
  const counts = new Map<RiskName, number>()
  for (const point of points) {
    const risk = SCORE_TO_RISK[point.risks[hour] ?? 0] ?? "low"
    counts.set(risk, (counts.get(risk) ?? 0) + 1)
  }
  const present = (Object.keys(RISK_LABELS) as RiskName[])
    .filter((risk) => counts.has(risk))
    .reverse()
  if (present.length === 1) {
    return `${RISK_LABELS[present[0]]} at every corridor sample`
  }
  return present.map((risk) => `${RISK_LABELS[risk]} ${counts.get(risk)}`).join(" · ")
}
