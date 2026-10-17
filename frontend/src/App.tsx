import { Map, NavigationControl } from "maplibre-gl"
import { useEffect, useRef } from "react"
import "maplibre-gl/dist/maplibre-gl.css"

const MAP_STYLE = "https://tiles.openfreemap.org/styles/liberty"

export default function App() {
  const container = useRef<HTMLDivElement>(null)

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
    return () => {
      map.remove()
    }
  }, [])

  return (
    <main className="shell">
      <div ref={container} className="map" />
    </main>
  )
}
