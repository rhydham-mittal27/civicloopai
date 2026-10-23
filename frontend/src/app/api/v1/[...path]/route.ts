import type { NextRequest } from "next/server";

/**
 * The web app talks to the API through this proxy so the sign-in token never reaches page scripts.
 *
 * Signing in stores the token in an httpOnly cookie (JavaScript cannot read it, so an injected script cannot steal it)
 * and hands the page only a harmless marker (who, which role, until when) to draw the right screens. Every other
 * request has the cookie turned into the Authorization header here, then goes on to the API.
 */
export const dynamic = "force-dynamic";

const BACKEND = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
const COOKIE = "civicloop_session";
const HOP_BY_HOP = new Set(["connection", "keep-alive", "transfer-encoding", "content-length", "host", "content-encoding", "cookie", "authorization"]);

type Ctx = { params: Promise<{ path: string[] }> };

function b64url(text: string): string {
  return Buffer.from(text, "utf-8").toString("base64url");
}

function tokenPayload(token: string): { sub: string; role: string; exp: number } | null {
  try {
    const json = JSON.parse(Buffer.from(token.split(".")[0], "base64url").toString("utf-8"));
    return typeof json.exp === "number" ? json : null;
  } catch {
    return null;
  }
}

function cookieHeader(value: string, maxAgeSeconds: number): string {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${COOKIE}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${Math.max(0, Math.floor(maxAgeSeconds))}${secure}`;
}

function sameSite(request: NextRequest): boolean {
  // a form on another site must not be able to act with this person's cookie
  const origin = request.headers.get("origin");
  return !origin || origin === request.nextUrl.origin;
}

async function forward(request: NextRequest, { params }: Ctx): Promise<Response> {
  const { path } = await params;
  const joined = path.join("/");
  const mutating = !["GET", "HEAD", "OPTIONS"].includes(request.method);
  if (mutating && !sameSite(request)) return Response.json({ detail: "Cross-site request refused" }, { status: 403 });

  if (joined === "auth/logout" && request.method === "POST") {
    return new Response(null, { status: 204, headers: { "Set-Cookie": cookieHeader("", 0) } });
  }

  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  const token = request.cookies.get(COOKIE)?.value;
  if (token && joined !== "auth/login") headers.set("Authorization", `Bearer ${token}`);

  const init: RequestInit & { duplex?: "half" } = { method: request.method, headers, redirect: "manual" };
  if (mutating) {
    init.body = request.body;
    init.duplex = "half";
  }
  let upstream: Response;
  try {
    upstream = await fetch(`${BACKEND}/api/v1/${joined}${request.nextUrl.search}`, init);
  } catch {
    return Response.json({ detail: "Cannot reach the CivicLoop server." }, { status: 502 });
  }

  const out = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) out.set(key, value);
  });

  if (joined === "auth/login" && request.method === "POST" && upstream.ok) {
    const body = (await upstream.json()) as { access_token?: string };
    const payload = body.access_token ? tokenPayload(body.access_token) : null;
    if (!body.access_token || !payload) return Response.json({ detail: "Sign-in failed" }, { status: 502 });
    out.set("Content-Type", "application/json");
    out.append("Set-Cookie", cookieHeader(body.access_token, payload.exp - Date.now() / 1000));
    // the page gets a marker, not the token: enough to know who is signed in and until when, useless to call the API
    const marker = `${b64url(JSON.stringify({ sub: payload.sub, role: payload.role, exp: payload.exp }))}.session`;
    return new Response(JSON.stringify({ access_token: marker, token_type: "session" }), { status: 200, headers: out });
  }

  if (upstream.status === 401 && token) out.append("Set-Cookie", cookieHeader("", 0)); // the API ended this sign-in
  return new Response(upstream.body, { status: upstream.status, headers: out });
}

export { forward as GET, forward as POST, forward as PUT, forward as PATCH, forward as DELETE, forward as HEAD };
