// Fake Stripe for end-to-end tests only (CI never contacts Stripe). The web server points
// stripe-node at it when E2E_FAKE_STRIPE_URL is set (refused outside localhost / on Railway).
//   node e2e/fake-stripe.mjs        (port FAKE_STRIPE_PORT, default 4466)
// It implements the API calls EdgeFront makes, simple hosted Checkout and Customer Portal pages,
// and sends webhooks signed exactly like Stripe's (t=…,v1=HMAC-SHA256) to FAKE_STRIPE_WEBHOOK_URL
// with FAKE_STRIPE_WEBHOOK_SECRET. Test controls live under /__ (fail a payment, recover, end).
import { createHmac, randomBytes } from "node:crypto";
import { createServer } from "node:http";

const port = Number(process.env.FAKE_STRIPE_PORT ?? 4466);
const base = `http://localhost:${port}`;
const WEBHOOK_URL =
  process.env.FAKE_STRIPE_WEBHOOK_URL ?? "http://localhost:3000/api/stripe/webhook";
const WEBHOOK_SECRET = process.env.FAKE_STRIPE_WEBHOOK_SECRET ?? "whsec_e2e_secret";
const DELAY_MS = Number(process.env.FAKE_STRIPE_WEBHOOK_DELAY_MS ?? 1500);
const DAY = 86400;

const id = (p) => `${p}_${randomBytes(8).toString("hex")}`;
const now = () => Math.floor(Date.now() / 1000);

const prices = new Map([
  ["price_e2e_premium", { id: "price_e2e_premium", object: "price", active: true, unit_amount: 2000, currency: "usd", recurring: { interval: "month", interval_count: 1 }, product: "prod_e2e" }],
]); // prettier-ignore
const customers = new Map(); // id -> customer
const sessions = new Map(); // id -> { params, customer, ... }
const subs = new Map(); // id -> subscription (raw, latest_invoice as id)
const invoices = new Map(); // id -> invoice
const idem = new Map(); // idempotency key -> response body

function body(req) {
  return new Promise((resolve) => {
    let data = "";
    req.on("data", (c) => (data += c));
    req.on("end", () => resolve(data));
  });
}

function invoiceFor(sub, status, amount) {
  const inv = {
    id: id("in"),
    object: "invoice",
    status,
    amount_due: amount,
    currency: "usd",
    created: now(),
    next_payment_attempt: status === "open" ? now() + 3 * DAY : null,
    parent: { type: "subscription_details", subscription_details: { subscription: sub.id } },
  };
  invoices.set(inv.id, inv);
  sub.latest_invoice = inv.id;
  return inv;
}

function view(sub, expand = []) {
  const out = structuredClone(sub);
  if (expand.includes("latest_invoice") && out.latest_invoice) out.latest_invoice = invoices.get(out.latest_invoice) ?? null;
  if (expand.includes("default_payment_method")) {
    out.default_payment_method = { id: "pm_e2e", object: "payment_method", type: "card", card: { brand: "visa", last4: "4242" } };
  }
  return out;
} // prettier-ignore

async function send(type, object) {
  const event = { id: id("evt"), object: "event", api_version: "2026-11-18.endive", created: now(), type, data: { object } };
  const payload = JSON.stringify(event);
  const t = now();
  const v1 = createHmac("sha256", WEBHOOK_SECRET).update(`${t}.${payload}`).digest("hex");
  try {
    const res = await fetch(WEBHOOK_URL, { method: "POST", headers: { "content-type": "application/json", "stripe-signature": `t=${t},v1=${v1}` }, body: payload });
    if (!res.ok) console.log(`webhook ${type} -> ${res.status}`);
  } catch (e) {
    console.log(`webhook ${type} failed: ${e.message}`);
  }
} // prettier-ignore

const later = (fn) => setTimeout(fn, DELAY_MS);

function html(res, title, inner) {
  res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
  res.end(
    `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${title}</title></head><body style="font-family:sans-serif;max-width:480px;margin:40px auto;padding:0 16px"><p><strong>FAKE STRIPE (tests)</strong></p>${inner}</body></html>`,
  );
}

createServer(async (req, res) => {
  const url = new URL(req.url, base);
  const p = url.pathname;
  const json = (status, obj) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(obj));
  };
  const raw = req.method === "POST" ? await body(req) : "";
  const form = new URLSearchParams(raw);
  const expand = [...url.searchParams.entries(), ...form.entries()]
    .filter(([k]) => k.startsWith("expand"))
    .map(([, v]) => v);
  const key = req.headers["idempotency-key"];
  const reply = (status, obj) => {
    if (key && status < 400) idem.set(key, obj);
    json(status, obj);
  };
  if (key && idem.has(key)) return json(200, idem.get(key));

  // ---------------------------------------------------------------- API (stripe-node)
  let m;
  if (req.method === "GET" && (m = p.match(/^\/v1\/prices\/([^/]+)$/))) {
    const price = prices.get(m[1]);
    return price
      ? json(200, price)
      : json(404, {
          error: {
            type: "invalid_request_error",
            code: "resource_missing",
            message: "No such price",
          },
        });
  }
  if (req.method === "POST" && p === "/v1/customers") {
    const c = {
      id: id("cus"),
      object: "customer",
      email: form.get("email"),
      name: form.get("name"),
      metadata: { user_id: form.get("metadata[user_id]") },
    };
    customers.set(c.id, c);
    return reply(200, c);
  }
  if (req.method === "POST" && p === "/v1/checkout/sessions") {
    const s = {
      id: id("cs_test"),
      object: "checkout.session",
      mode: form.get("mode"),
      customer: form.get("customer"),
      client_reference_id: form.get("client_reference_id"),
      price: form.get("line_items[0][price]"),
      trial_days: form.get("subscription_data[trial_period_days]")
        ? Number(form.get("subscription_data[trial_period_days]"))
        : null,
      payment_method_collection: form.get("payment_method_collection"),
      automatic_tax: form.get("automatic_tax[enabled]"),
      user_id: form.get("subscription_data[metadata][user_id]"),
      success_url: form.get("success_url"),
      cancel_url: form.get("cancel_url"),
    };
    s.url = `${base}/checkout/${s.id}`;
    sessions.set(s.id, s);
    return reply(200, s);
  }
  if ((m = p.match(/^\/v1\/subscriptions\/([^/]+)$/))) {
    const sub = subs.get(m[1]);
    if (!sub)
      return json(404, {
        error: {
          type: "invalid_request_error",
          code: "resource_missing",
          message: "No such subscription",
        },
      });
    if (req.method === "GET") return json(200, view(sub, expand));
    if (req.method === "DELETE") {
      Object.assign(sub, { status: "canceled", canceled_at: now(), ended_at: now() });
      later(() => send("customer.subscription.deleted", view(sub)));
      return reply(200, view(sub));
    }
  }
  if (req.method === "POST" && p === "/v1/invoices/create_preview") {
    const sub = subs.get(form.get("subscription"));
    if (!sub)
      return json(404, {
        error: {
          type: "invalid_request_error",
          code: "resource_missing",
          message: "No such subscription",
        },
      });
    const amount = sub.items.data[0].price.unit_amount;
    return json(200, {
      object: "invoice",
      subtotal: amount,
      total_taxes: [],
      total: amount,
      currency: "usd",
    });
  }
  if (req.method === "POST" && p === "/v1/billing_portal/sessions") {
    const ps = {
      id: id("bps"),
      object: "billing_portal.session",
      customer: form.get("customer"),
      return_url: form.get("return_url"),
    };
    ps.url = `${base}/portal/${ps.id}?customer=${ps.customer}&return=${encodeURIComponent(ps.return_url)}`;
    return reply(200, ps);
  }

  // ---------------------------------------------------------------- hosted pages (browser)
  if (req.method === "GET" && (m = p.match(/^\/checkout\/([^/]+)$/))) {
    const s = sessions.get(m[1]);
    if (!s) return json(404, { error: "no session" });
    const trial = s.trial_days
      ? `${s.trial_days}-day free trial, then $20.00/month`
      : "No trial: $20.00/month starting today";
    return html(
      res,
      "Fake Checkout",
      `<h1>Subscribe to EdgeFront Premium</h1><p data-testid="offer">${trial}</p><p>Card: 4242 4242 4242 4242</p><form method="post" action="/checkout/${s.id}/complete"><button type="submit">${s.trial_days ? "Start trial" : "Subscribe"}</button></form><p><a href="${s.cancel_url}">Back</a></p>`,
    );
  }
  if (req.method === "POST" && (m = p.match(/^\/checkout\/([^/]+)\/complete$/))) {
    const s = sessions.get(m[1]);
    if (!s) return json(404, { error: "no session" });
    const price = prices.get(s.price);
    const trialEnd = s.trial_days ? now() + s.trial_days * DAY : null;
    const sub = {
      id: id("sub"),
      object: "subscription",
      customer: s.customer,
      status: trialEnd ? "trialing" : "active",
      cancel_at_period_end: false,
      cancel_at: null,
      canceled_at: null,
      ended_at: null,
      trial_end: trialEnd,
      metadata: { user_id: s.user_id },
      latest_invoice: null,
      items: {
        object: "list",
        data: [
          {
            id: id("si"),
            object: "subscription_item",
            price,
            quantity: 1,
            current_period_start: now(),
            current_period_end: trialEnd ?? now() + 30 * DAY,
          },
        ],
      },
    };
    invoiceFor(sub, "paid", trialEnd ? 0 : price.unit_amount);
    subs.set(sub.id, sub);
    s.subscription = sub.id;
    s.status = "complete";
    later(async () => {
      await send("checkout.session.completed", {
        id: s.id,
        object: "checkout.session",
        mode: "subscription",
        customer: s.customer,
        subscription: sub.id,
      });
      await send("customer.subscription.created", view(sub));
    });
    res.writeHead(303, { location: s.success_url });
    return res.end();
  }
  if (req.method === "GET" && (m = p.match(/^\/portal\/([^/]+)$/))) {
    const customer = url.searchParams.get("customer");
    const ret = url.searchParams.get("return");
    const sub = [...subs.values()].find((x) => x.customer === customer && x.status !== "canceled");
    const action = sub?.cancel_at_period_end ? "resume" : "cancel";
    const form = sub
      ? `<form method="post" action="/portal/${m[1]}/${action}?sub=${sub.id}&return=${encodeURIComponent(ret)}"><button type="submit">${action === "cancel" ? "Cancel plan" : "Renew plan"}</button></form>`
      : "<p>No active subscription.</p>";
    return html(
      res,
      "Fake Customer Portal",
      `<h1>Manage your subscription</h1><p>Visa •••• 4242</p>${form}<p><a href="${ret}">Return to EdgeFront</a></p>`,
    );
  }
  if (req.method === "POST" && (m = p.match(/^\/portal\/[^/]+\/(cancel|resume)$/))) {
    const sub = subs.get(url.searchParams.get("sub"));
    if (sub) {
      sub.cancel_at_period_end = m[1] === "cancel";
      later(() => send("customer.subscription.updated", view(sub)));
    }
    res.writeHead(303, { location: url.searchParams.get("return") });
    return res.end();
  }

  // ---------------------------------------------------------------- test controls
  if (req.method === "GET" && p === "/health") return json(200, { ok: true });
  if (req.method === "GET" && p === "/__by-email") {
    const email = url.searchParams.get("email");
    const cs = [...customers.values()].filter((c) => c.email === email);
    const ids = new Set(cs.map((c) => c.id));
    return json(200, {
      customers: cs,
      subscriptions: [...subs.values()]
        .filter((s) => ids.has(s.customer))
        .map((s) => view(s, ["latest_invoice"])),
      sessions: [...sessions.values()].filter((s) => ids.has(s.customer)),
    });
  }
  if (
    req.method === "POST" &&
    (m = p.match(/^\/__subscriptions\/([^/]+)\/(fail_payment|recover|end)$/))
  ) {
    const sub = subs.get(m[1]);
    if (!sub) return json(404, { error: "no subscription" });
    const price = sub.items.data[0].price;
    if (m[2] === "fail_payment") {
      Object.assign(sub, {
        status: "past_due",
        trial_end: sub.trial_end && sub.trial_end > now() ? now() - 60 : sub.trial_end,
      });
      invoiceFor(sub, "open", price.unit_amount);
      send("invoice.payment_failed", { ...invoices.get(sub.latest_invoice) }).then(() =>
        send("customer.subscription.updated", view(sub)),
      );
    } else if (m[2] === "recover") {
      sub.status = "active";
      sub.items.data[0].current_period_end = now() + 30 * DAY;
      invoiceFor(sub, "paid", price.unit_amount);
      send("invoice.paid", { ...invoices.get(sub.latest_invoice) }).then(() =>
        send("customer.subscription.updated", view(sub)),
      );
    } else {
      Object.assign(sub, { status: "canceled", canceled_at: now(), ended_at: now() });
      send("customer.subscription.deleted", view(sub));
    }
    return json(200, view(sub));
  }
  json(404, {
    error: {
      type: "invalid_request_error",
      message: `fake stripe: ${req.method} ${p} not implemented`,
    },
  });
}).listen(port, () => console.log(`fake stripe on :${port}`));
