import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { chargeDate, renewalDisclosure, taxWording } from "@/lib/billing/disclosure";

import { renderLegal, slug } from "./markdown";

describe("renewal disclosure (ROSCA / Florida)", () => {
  const price = { unitAmount: 2000, currency: "usd", interval: "month", taxBehavior: "exclusive" };
  const now = new Date("2026-11-28T15:00:00Z");
  it("trial: the owner's text with the price from Stripe and the date for the viewer", () => {
    const d = renewalDisclosure(price, {
      trial: true,
      trialDays: 7,
      now,
      timeZone: "America/New_York",
    });
    expect(d.text).toBe(
      "7-day free trial, then $20/month plus applicable tax, renewing automatically each month until you cancel. Your card is charged on December 5, 2026 unless you cancel before then. Cancel anytime in Account → Manage billing.",
    );
    expect(d.price).toBe("$20/month plus applicable tax");
  });
  it("the date follows the viewer's time zone", () => {
    const late = new Date("2026-11-29T03:30:00Z"); // still Nov 28 in Los Angeles
    expect(chargeDate(late, 7, "America/Los_Angeles")).toBe("December 5, 2026");
    expect(chargeDate(late, 7, "Asia/Dhaka")).toBe("December 6, 2026");
  });
  it("tax wording comes from the Stripe price; no trial → charged today", () => {
    expect(taxWording("exclusive")).toBe("plus applicable tax");
    expect(taxWording("inclusive")).toBe("including applicable tax");
    expect(
      renewalDisclosure({ ...price, unitAmount: 2500 }, { trial: false, trialDays: 7, now }).text,
    ).toBe(
      "$25/month plus applicable tax, renewing automatically each month until you cancel. Your card is charged today and then at the start of each month. Cancel anytime in Account → Manage billing.",
    );
  });
});

describe("legal markdown", () => {
  it("headings become anchors; text is escaped; placeholders are highlighted", () => {
    const r = renderLegal(
      "# Terms\n\n**Effective date:** [OWNER: date]\n\n## 1. Who can use EdgeFront\n- **18+** & <b>x</b>\n- see [Privacy](/privacy)\n\n| A | B |\n|---|---|\n| 1 | `2` |\n",
    );
    expect(r.title).toBe("Terms");
    expect(r.effective).toBe(
      '<strong>Effective date:</strong> <mark class="legal-todo">[OWNER: date]</mark>',
    );
    expect(r.headings).toEqual([
      { id: "1-who-can-use-edgefront", text: "1. Who can use EdgeFront" },
    ]);
    expect(r.html).toContain('<h2 id="1-who-can-use-edgefront">');
    expect(r.html).not.toContain("Effective date");
    expect(r.html).toContain("<li><strong>18+</strong> &amp; &lt;b&gt;x&lt;/b&gt;</li>");
    expect(r.html).toContain('<a href="/privacy">Privacy</a>');
    expect(r.html).toContain("<td><code>2</code></td>");
    expect(slug("5. Premium subscription, free trial and automatic renewal")).toBe(
      "5-premium-subscription-free-trial-and-automatic-renewal",
    );
  });
});

describe("placeholder check (fails the build while any [OWNER:/[VERIFY: is left)", () => {
  const run = (docs: Record<string, string>, env: Record<string, string> = {}) => {
    const dir = mkdtempSync(join(tmpdir(), "legal-"));
    for (const n of ["terms", "privacy", "refund"])
      writeFileSync(join(dir, `${n}.md`), docs[n] ?? `# ${n}\n`);
    return spawnSync(process.execPath, ["scripts/gen-legal.mjs"], {
      env: {
        ...process.env,
        ALLOW_LEGAL_PLACEHOLDERS: "",
        LEGAL_DIR: dir,
        LEGAL_OUT: join(dir, "out.json"),
        ...env,
      },
      encoding: "utf8",
    });
  };
  it("fails on [OWNER: …] and [VERIFY: …], passes when none are left", () => {
    expect(run({ terms: "# T\n[OWNER: name]\n" }).status).toBe(1);
    expect(run({ refund: "# R\n[VERIFY: days]\n" }).status).toBe(1);
    expect(run({}).status).toBe(0);
    expect(run({ terms: "# T\n[OWNER: name]\n" }, { ALLOW_LEGAL_PLACEHOLDERS: "1" }).status).toBe(
      0,
    );
  });
});
