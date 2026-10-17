import type { RiskName } from "./types"

export const RISK_COLORS: Record<RiskName, string> = {
  low: "#1f8a4c",
  moderate: "#c48a00",
  high: "#d85a0a",
  severe: "#c62828",
  no_travel: "#6a1b9a",
}

export const RISK_LABELS: Record<RiskName, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
  no_travel: "No travel",
}

export const SCORE_TO_RISK: RiskName[] = ["low", "moderate", "high", "severe", "no_travel"]

export const ROUTE_COLORS = ["#1d4e89", "#0f6e6e", "#8a4b08"]

export function averageRiskLabel(score: number): RiskName {
  if (score >= 3.5) return "no_travel"
  if (score >= 2.5) return "severe"
  if (score >= 1.5) return "high"
  if (score >= 0.5) return "moderate"
  return "low"
}
