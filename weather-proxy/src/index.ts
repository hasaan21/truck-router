const UPSTREAMS: Record<string, string> = {
  "/v1/forecast": "https://api.open-meteo.com/v1/forecast",
  "/v1/search": "https://geocoding-api.open-meteo.com/v1/search",
}

type ProxyEnv = Env & { PROXY_TOKEN: string }

export default {
  async fetch(request, env: ProxyEnv): Promise<Response> {
    if (request.method !== "GET") {
      return new Response("Method not allowed", { status: 405 })
    }
    const url = new URL(request.url)
    const upstream = UPSTREAMS[url.pathname]
    if (!upstream) {
      return new Response("Not found", { status: 404 })
    }
    const authorized = await tokensMatch(request.headers.get("X-Weather-Token") ?? "", env.PROXY_TOKEN)
    if (!authorized) {
      return new Response("Unauthorized", { status: 401 })
    }
    const target = new URL(upstream)
    target.search = url.search
    const response = await fetch(target, { headers: { Accept: "application/json" } })
    return new Response(response.body, {
      status: response.status,
      headers: { "Content-Type": response.headers.get("Content-Type") ?? "application/json" },
    })
  },
} satisfies ExportedHandler<ProxyEnv>

async function tokensMatch(provided: string, expected: string): Promise<boolean> {
  const encoder = new TextEncoder()
  const [providedHash, expectedHash] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(provided)),
    crypto.subtle.digest("SHA-256", encoder.encode(expected)),
  ])
  return crypto.subtle.timingSafeEqual(providedHash, expectedHash)
}
