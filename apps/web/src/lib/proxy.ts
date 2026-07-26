import { auth } from "@clerk/nextjs/server";

// SERVER-ONLY. The Backend-for-Frontend seam: the browser calls same-origin
// /api/* route handlers; those handlers call THIS to mint a Clerk JWT
// server-side and proxy to the FastAPI backend. Two payoffs:
//   1. The backend URL (API_BASE_URL) never reaches the browser → no CORS, the
//      backend isn't publicly addressable from the SPA.
//   2. The Clerk token is minted + attached server-side → never exposed to a
//      cross-origin client fetch.

const API_BASE_URL = process.env.API_BASE_URL ?? "http://localhost:8000";

/** Fetch the FastAPI backend with a server-minted Clerk Bearer token.
 * Returns a 401 Response (not a throw) when there's no session, so route
 * handlers can forward it verbatim. */
export async function authedBackendFetch(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const { getToken } = await auth();
  const token = await getToken();
  if (!token) {
    return new Response(JSON.stringify({ detail: "unauthenticated" }), {
      status: 401,
      headers: { "Content-Type": "application/json" },
    });
  }
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

/** Proxy a JSON backend call and return the upstream status + body verbatim.
 * Forwards Retry-After on 429 so the client can show a countdown. */
export async function proxyJson(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const upstream = await authedBackendFetch(path, init);
  const body = await upstream.text();
  const headers = new Headers({ "Content-Type": "application/json" });
  const retryAfter = upstream.headers.get("Retry-After");
  if (retryAfter) headers.set("Retry-After", retryAfter);
  return new Response(body, { status: upstream.status, headers });
}
