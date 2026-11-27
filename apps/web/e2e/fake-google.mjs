// Fake Google OAuth server for end-to-end tests only (never contacted by production code).
// The web server registers it as provider "google" when E2E_FAKE_GOOGLE_URL is set.
//   node e2e/fake-google.mjs            (port FAKE_GOOGLE_PORT, default 4455)
// Tests choose who signs in next, per browser context: cookie fake_google_identity=<base64url JSON
// {"sub","email","name","email_verified"}> (localhost cookies are shared across ports), or
// globally with POST /__identity.
import { createServer } from "node:http";
import { randomBytes } from "node:crypto";

const port = Number(process.env.FAKE_GOOGLE_PORT ?? 4455);
let nextIdentity = {
  sub: "g-default",
  email: "google.user@example.org",
  name: "Google User",
  email_verified: true,
};
const codes = new Map(); // code -> identity
const tokens = new Map(); // access token -> identity

function body(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(data));
  });
}

function cookieIdentity(req) {
  const m = /(?:^|;\s*)fake_google_identity=([^;]+)/.exec(req.headers.cookie ?? "");
  if (!m) return null;
  try {
    return JSON.parse(Buffer.from(m[1], "base64url").toString("utf8"));
  } catch {
    return null;
  }
}

createServer(async (req, res) => {
  const url = new URL(req.url, `http://localhost:${port}`);
  const json = (status, obj) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  if (req.method === "POST" && url.pathname === "/__identity") {
    nextIdentity = JSON.parse((await body(req)) || "{}");
    return json(200, { ok: true });
  }
  if (req.method === "GET" && url.pathname === "/health") return json(200, { ok: true });
  if (req.method === "GET" && url.pathname === "/authorize") {
    const redirect = new URL(url.searchParams.get("redirect_uri"));
    const code = randomBytes(12).toString("hex");
    codes.set(code, cookieIdentity(req) ?? nextIdentity);
    redirect.searchParams.set("code", code);
    redirect.searchParams.set("state", url.searchParams.get("state") ?? "");
    res.writeHead(302, { location: redirect.toString() });
    return res.end();
  }
  if (req.method === "POST" && url.pathname === "/token") {
    const form = new URLSearchParams(await body(req));
    const identity = codes.get(form.get("code"));
    if (!identity) return json(400, { error: "invalid_grant" });
    codes.delete(form.get("code"));
    const access = randomBytes(16).toString("hex");
    tokens.set(access, identity);
    return json(200, {
      access_token: access,
      token_type: "Bearer",
      expires_in: 3600,
      scope: "openid email profile",
    });
  }
  if (req.method === "GET" && url.pathname === "/userinfo") {
    const identity = tokens.get((req.headers.authorization ?? "").replace(/^Bearer /, ""));
    if (!identity) return json(401, { error: "invalid_token" });
    return json(200, { ...identity, id: identity.sub });
  }
  json(404, { error: "not found" });
}).listen(port, () => console.log(`fake google on :${port}`));
