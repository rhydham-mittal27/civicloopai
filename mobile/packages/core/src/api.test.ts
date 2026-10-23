import { describe, expect, it, vi } from "vitest";
import { ApiError, createApi, messageFrom, normaliseServerUrl } from "./api";
import { agoFromSeconds, isValidPincode, whenLabel } from "./format";

function fakeFetch(status: number, body: unknown) {
  return vi.fn(async (_url: string | URL | Request, _init?: RequestInit) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
}

function client(fetchImpl: typeof fetch, token: string | null = "tok", onUnauthorized?: () => void) {
  return createApi({ baseUrl: () => "http://10.0.0.5:8000/", getToken: () => token, fetch: fetchImpl, onUnauthorized });
}

describe("server address", () => {
  it("adds http and drops trailing slashes", () => {
    expect(normaliseServerUrl(" 192.168.1.20:8000/ ")).toBe("http://192.168.1.20:8000");
    expect(normaliseServerUrl("https://civic.example.org//")).toBe("https://civic.example.org");
    expect(normaliseServerUrl("")).toBe("");
  });
});

describe("requests", () => {
  it("sends the token and calls the versioned path", async () => {
    const f = fakeFetch(200, []);
    await client(f as unknown as typeof fetch).listIncidents("approved", 20);
    const [url, init] = f.mock.calls[0]!;
    expect(String(url)).toBe("http://10.0.0.5:8000/api/v1/incidents?status_filter=approved&limit=20");
    expect((init!.headers as Record<string, string>).Authorization).toBe("Bearer tok");
  });

  it("posts json with a content type", async () => {
    const f = fakeFetch(200, { access_token: "t" });
    await client(f as unknown as typeof fetch, null).login("a@b.co", "pw");
    const [, init] = f.mock.calls[0]!;
    expect(init!.method).toBe("POST");
    expect((init!.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(JSON.parse(String(init!.body))).toEqual({ email: "a@b.co", password: "pw" });
    expect((init!.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("turns a server error into a readable message", async () => {
    const f = fakeFetch(409, { detail: "Email is already registered" });
    await expect(client(f as unknown as typeof fetch, null).register({ name: "A", email: "a@b.co", password: "x", city: "Pune", pincode: "411001" })).rejects.toMatchObject({
      message: "Email is already registered",
      status: 409,
    });
  });

  it("joins validation problems", () => {
    expect(messageFrom({ detail: [{ msg: "Field required" }, { msg: "Too short" }] }, "x")).toBe("Field required. Too short");
    expect(messageFrom(null, "fallback")).toBe("fallback");
  });

  it("signs the person out when the server rejects a held token", async () => {
    const out = vi.fn();
    const f = fakeFetch(401, { detail: "Token has expired" });
    await expect(client(f as unknown as typeof fetch, "old", out).me()).rejects.toBeInstanceOf(ApiError);
    expect(out).toHaveBeenCalledOnce();
  });

  it("does not call that a sign-out when nobody was signed in", async () => {
    const out = vi.fn();
    const f = fakeFetch(401, { detail: "Invalid credentials" });
    await expect(client(f as unknown as typeof fetch, null, out).login("a", "b")).rejects.toBeInstanceOf(ApiError);
    expect(out).not.toHaveBeenCalled();
  });

  it("explains when the server cannot be reached", async () => {
    const f = vi.fn(async () => {
      throw new TypeError("Network request failed");
    });
    await expect(client(f as unknown as typeof fetch).me()).rejects.toMatchObject({ status: 0, message: expect.stringContaining("Cannot reach the server") });
  });

  it("asks for an address before any call when none is set", async () => {
    const api = createApi({ baseUrl: () => "", getToken: () => null, fetch: fakeFetch(200, {}) as unknown as typeof fetch });
    await expect(api.me()).rejects.toMatchObject({ message: "Set the server address first." });
  });

  it("ping reports whether the server answers", async () => {
    expect(await client(fakeFetch(200, { status: "ok" }) as unknown as typeof fetch).ping()).toBe(true);
    const down = vi.fn(async () => {
      throw new Error("down");
    });
    expect(await client(down as unknown as typeof fetch).ping()).toBe(false);
  });

  it("builds the image address and its headers for the image component", async () => {
    const api = client(fakeFetch(200, {}) as unknown as typeof fetch);
    expect(api.mediaUrl("m1")).toBe("http://10.0.0.5:8000/api/v1/media/m1/content");
    expect(await api.authHeaders()).toEqual({ Authorization: "Bearer tok" });
  });

  it("uploads a photo as a multipart form without forcing a content type", async () => {
    const f = fakeFetch(201, { id: "m" });
    await client(f as unknown as typeof fetch).submitEvidence("inc1", { uri: "file:///a.jpg", name: "a.jpg", type: "image/jpeg" }, "all clear");
    const [url, init] = f.mock.calls[0]!;
    expect(String(url)).toContain("/incidents/inc1/verification");
    expect(init!.body).toBeInstanceOf(FormData);
    expect((init!.headers as Record<string, string>)["Content-Type"]).toBeUndefined();
    expect((init!.body as FormData).get("notes")).toBe("all clear");
  });
});

describe("helpers", () => {
  it("words how long ago something happened", () => {
    expect(agoFromSeconds(null)).toBe("never");
    expect(agoFromSeconds(3)).toBe("just now");
    expect(agoFromSeconds(40)).toBe("40 s ago");
    expect(agoFromSeconds(600)).toBe("10 min ago");
    expect(agoFromSeconds(7200)).toBe("2 h ago");
  });

  it("labels today, yesterday and older dates", () => {
    const now = new Date(2026, 9, 24, 15, 0);
    expect(whenLabel(new Date(2026, 9, 24, 9, 5).toISOString(), now)).toBe("Today 09:05");
    expect(whenLabel(new Date(2026, 9, 23, 18, 30).toISOString(), now)).toBe("Yesterday 18:30");
    expect(whenLabel(new Date(2026, 9, 12, 8, 0).toISOString(), now)).toBe("12 Oct");
  });

  it("checks pincodes the way the server does", () => {
    expect(isValidPincode("160017")).toBe(true);
    expect(isValidPincode("060017")).toBe(false);
    expect(isValidPincode("16001")).toBe(false);
    expect(isValidPincode("16001a")).toBe(false);
  });
});
