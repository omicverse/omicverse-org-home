const DOCS_URL = "https://omicverse.readthedocs.io/";
const DOCS_PATHS = new Set(["/learn", "/learn/", "/learn.html"]);

// Usage analytics: the omicverse Python package reports to
// https://omicverse.org/analytics/*, which is forwarded to the collector
// running on omicos.cn. Override with the ANALYTICS_UPSTREAM variable.
const ANALYTICS_PREFIX = "/analytics/";
const DEFAULT_ANALYTICS_UPSTREAM = "https://omicos.cn/ov-analytics";

async function proxyAnalytics(request, url, env) {
  if (request.method !== "GET" && request.method !== "HEAD") {
    return new Response("Method Not Allowed", { status: 405, headers: { Allow: "GET, HEAD" } });
  }

  const upstreamBase = (env.ANALYTICS_UPSTREAM || DEFAULT_ANALYTICS_UPSTREAM).replace(/\/+$/, "");
  const target = upstreamBase + "/" + url.pathname.slice(ANALYTICS_PREFIX.length) + url.search;
  const clientIp = request.headers.get("CF-Connecting-IP") || "";

  const headers = new Headers();
  headers.set("User-Agent", request.headers.get("User-Agent") || "");
  headers.set("X-Forwarded-For", clientIp);
  headers.set("X-Real-IP", clientIp);
  headers.set("X-Forwarded-Host", url.host);
  headers.set("X-Forwarded-Proto", "https");

  try {
    const upstream = await fetch(target, {
      method: request.method,
      headers,
      redirect: "manual",
      signal: AbortSignal.timeout(8000),
    });
    const response = new Response(upstream.body, upstream);
    response.headers.set("Cache-Control", "no-store");
    response.headers.set("Access-Control-Allow-Origin", "*");
    return response;
  } catch (err) {
    return new Response(JSON.stringify({ error: "analytics upstream unavailable" }), {
      status: 502,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname.startsWith(ANALYTICS_PREFIX)) {
      return proxyAnalytics(request, url, env);
    }

    if (DOCS_PATHS.has(url.pathname)) {
      return Response.redirect(DOCS_URL, 302);
    }

    return env.ASSETS.fetch(request);
  },
};
