import { useEffect, useId, useState } from "react"
import { searchPlaces } from "../api"
import type { Place } from "../types"

interface PlaceFieldProps {
  label: string
  value: Place | null
  onChange: (place: Place | null) => void
}

export function PlaceField({ label, value, onChange }: PlaceFieldProps) {
  const listId = useId()
  const [text, setText] = useState(value?.label ?? "")
  const [options, setOptions] = useState<Place[]>([])
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [highlight, setHighlight] = useState(0)

  useEffect(() => {
    setText(value?.label ?? "")
  }, [value])

  useEffect(() => {
    const query = text.trim()
    if (query.length < 2 || query === value?.label) {
      setOptions([])
      setBusy(false)
      return
    }
    const controller = new AbortController()
    const timer = window.setTimeout(async () => {
      try {
        setBusy(true)
        const places = await searchPlaces(query, controller.signal)
        setOptions(places)
        setHighlight(0)
        setOpen(true)
        setError(null)
      } catch (caught) {
        if (caught instanceof DOMException && caught.name === "AbortError") {
          return
        }
        setOptions([])
        setError(caught instanceof Error ? caught.message : "Place search failed.")
        setOpen(true)
      } finally {
        setBusy(false)
      }
    }, 250)
    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [text, value])

  function choose(place: Place) {
    onChange(place)
    setText(place.label)
    setOpen(false)
    setOptions([])
  }

  return (
    <label className="field" onBlur={(event) => {
      if (!event.currentTarget.contains(event.relatedTarget)) {
        setOpen(false)
      }
    }}>
      <span>{label}</span>
      <input
        value={text}
        role="combobox"
        aria-expanded={open}
        aria-controls={listId}
        aria-autocomplete="list"
        placeholder="City or address"
        onChange={(event) => {
          const next = event.target.value
          setText(next)
          if (value && next !== value.label) {
            onChange(null)
          }
          setOpen(true)
        }}
        onFocus={() => {
          if (options.length > 0 || error) {
            setOpen(true)
          }
        }}
        onKeyDown={(event) => {
          if (!open || options.length === 0) {
            return
          }
          if (event.key === "ArrowDown") {
            event.preventDefault()
            setHighlight((current) => (current + 1) % options.length)
          } else if (event.key === "ArrowUp") {
            event.preventDefault()
            setHighlight((current) => (current - 1 + options.length) % options.length)
          } else if (event.key === "Enter" && options[highlight]) {
            event.preventDefault()
            choose(options[highlight])
          } else if (event.key === "Escape") {
            setOpen(false)
          }
        }}
      />
      {open && (busy || error || options.length > 0 || text.trim().length >= 2) ? (
        <ul id={listId} className="suggestions" role="listbox">
          {busy ? <li className="suggestion-status">Searching…</li> : null}
          {error ? <li className="suggestion-status">{error}</li> : null}
          {!busy && !error && options.length === 0 ? (
            <li className="suggestion-status">No matching places.</li>
          ) : null}
          {options.map((place, index) => (
            <li key={`${place.label}-${place.lat}-${place.lon}`}>
              <button
                type="button"
                role="option"
                aria-selected={index === highlight}
                className={index === highlight ? "active" : undefined}
                onMouseEnter={() => setHighlight(index)}
                onClick={() => choose(place)}
              >
                {place.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </label>
  )
}
