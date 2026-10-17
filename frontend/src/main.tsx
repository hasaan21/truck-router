import { setWorkerUrl } from "maplibre-gl"
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url"
import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import App from "./App"
import "./styles.css"

// Vite's prebundled MapLibre looks for its worker beside the bundle and never starts it.
setWorkerUrl(maplibreWorkerUrl)

const root = document.getElementById("root")
if (!root) {
  throw new Error("Root element is missing.")
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
