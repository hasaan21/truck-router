import type { PlannedRoute, RiskName } from "./types"

const EARTH_RADIUS_MILES = 3958.7613

export interface RiskSegment {
  routeId: string
  risk: RiskName
  coordinates: [number, number][]
}

export function riskSegments(route: PlannedRoute): RiskSegment[] {
  const coordinates = route.geometry.coordinates
  const total = route.checkpoints[route.checkpoints.length - 1]?.mile ?? 0
  if (route.checkpoints.length < 2 || total <= 0) {
    return [
      {
        routeId: route.id,
        risk: route.checkpoints[0]?.risk ?? "low",
        coordinates,
      },
    ]
  }
  const segments: RiskSegment[] = []
  for (let index = 0; index < route.checkpoints.length - 1; index += 1) {
    const current = route.checkpoints[index]
    const next = route.checkpoints[index + 1]
    const sliced = sliceLine(coordinates, current.mile / total, next.mile / total)
    if (sliced.length >= 2) {
      segments.push({ routeId: route.id, risk: current.risk, coordinates: sliced })
    }
  }
  return segments
}

function sliceLine(
  coordinates: [number, number][],
  startFraction: number,
  endFraction: number,
): [number, number][] {
  const cumulative = cumulativeMiles(coordinates)
  const total = cumulative[cumulative.length - 1] ?? 0
  if (total === 0) {
    return coordinates
  }
  const start = startFraction * total
  const end = endFraction * total
  const points: [number, number][] = [pointAt(coordinates, cumulative, start)]
  for (let index = 1; index < cumulative.length - 1; index += 1) {
    if (cumulative[index] > start && cumulative[index] < end) {
      points.push(coordinates[index])
    }
  }
  points.push(pointAt(coordinates, cumulative, end))
  return points
}

function cumulativeMiles(coordinates: [number, number][]): number[] {
  const cumulative = [0]
  for (let index = 1; index < coordinates.length; index += 1) {
    const [lon1, lat1] = coordinates[index - 1]
    const [lon2, lat2] = coordinates[index]
    cumulative.push(cumulative[index - 1] + haversineMiles(lon1, lat1, lon2, lat2))
  }
  return cumulative
}

function pointAt(
  coordinates: [number, number][],
  cumulative: number[],
  mile: number,
): [number, number] {
  if (mile <= 0) {
    return coordinates[0]
  }
  const last = cumulative[cumulative.length - 1] ?? 0
  if (mile >= last) {
    return coordinates[coordinates.length - 1]
  }
  for (let index = 0; index < cumulative.length - 1; index += 1) {
    const start = cumulative[index]
    const end = cumulative[index + 1]
    if (mile > end && index < cumulative.length - 2) {
      continue
    }
    const span = end - start
    if (span === 0) {
      return coordinates[index]
    }
    const ratio = (mile - start) / span
    const [lon1, lat1] = coordinates[index]
    const [lon2, lat2] = coordinates[index + 1]
    return [lon1 + ratio * (lon2 - lon1), lat1 + ratio * (lat2 - lat1)]
  }
  return coordinates[coordinates.length - 1]
}

function haversineMiles(lon1: number, lat1: number, lon2: number, lat2: number): number {
  const phi1 = (lat1 * Math.PI) / 180
  const phi2 = (lat2 * Math.PI) / 180
  const dPhi = ((lat2 - lat1) * Math.PI) / 180
  const dLambda = ((lon2 - lon1) * Math.PI) / 180
  const a =
    Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLambda / 2) ** 2
  return 2 * EARTH_RADIUS_MILES * Math.asin(Math.min(1, Math.sqrt(a)))
}
