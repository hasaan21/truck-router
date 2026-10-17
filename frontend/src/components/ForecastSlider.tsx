import { addHours, formatWhen } from "../format"

interface ForecastSliderProps {
  originTime: string
  hour: number
  playing: boolean
  onHour: (hour: number) => void
  onToggle: () => void
}

export function ForecastSlider({
  originTime,
  hour,
  playing,
  onHour,
  onToggle,
}: ForecastSliderProps) {
  return (
    <div className="slider">
      <div className="slider-top">
        <span>Corridor forecast</span>
        <strong>{formatWhen(addHours(originTime, hour))}</strong>
      </div>
      <div className="slider-row">
        <button type="button" className="ghost" onClick={onToggle}>
          {playing ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          min={0}
          max={47}
          value={hour}
          aria-valuetext={`${hour} hours after departure`}
          aria-label="Hours after departure"
          onChange={(event) => onHour(Number(event.target.value))}
        />
        <span className="hour-chip">+{hour}h</span>
      </div>
    </div>
  )
}
