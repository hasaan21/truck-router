import type { Place, PlanRequest, PlanResponse } from "./types"

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const response = await fetch(`/api/geocode/?q=${encodeURIComponent(query)}`, { signal })
  const payload = await readJson(response)
  if (!response.ok) {
    throw new Error(detail(payload, "Place search failed."))
  }
  return payload as Place[]
}

export async function planTrip(body: PlanRequest): Promise<PlanResponse> {
  const response = await fetch("/api/plan/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  })
  const payload = await readJson(response)
  if (!response.ok) {
    throw new Error(detail(payload, "Could not plan that trip."))
  }
  return payload as PlanResponse
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json()
  } catch {
    return {}
  }
}

function detail(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const message = (payload as { detail?: unknown }).detail
    if (typeof message === "string" && message.trim()) {
      return message
    }
  }
  return fallback
}
