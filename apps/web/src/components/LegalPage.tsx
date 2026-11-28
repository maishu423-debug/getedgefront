import legal from "@/generated/legal.json";
import { renderLegal } from "@/lib/legal/markdown";

import { PageShell } from "./Chrome";

export type LegalDoc = "terms" | "privacy" | "refund";

/**
 * /terms, /privacy and /refund (v2 Part 2): the owner's documents exactly as written (from
 * content/legal, copied at build time), headings as anchors, the effective date at the top.
 * Public pages: no sign-in needed (Google's brand verification reads /privacy).
 */
export function LegalPage({ doc }: { doc: LegalDoc }) {
  const { title, effective, html, headings } = renderLegal(legal[doc]);
  return (
    <PageShell>
      <main
        id="main"
        className="mx-auto flex w-full max-w-[760px] flex-col gap-6 px-4 pt-10 pb-16 sm:px-8"
      >
        <h1 className="font-display text-[36px] font-bold tracking-[-0.02em]">{title}</h1>
        {effective ? (
          <p
            className="legal -mt-3 text-[15px]"
            data-testid="effective-date"
            dangerouslySetInnerHTML={{ __html: effective }}
          />
        ) : null}
        {headings.length > 2 ? (
          <nav aria-label="On this page" className="rounded-[12px] border border-border bg-surface px-5 py-4">
            <p className="mb-2 text-[12px] font-semibold tracking-[.06em] text-muted-2 uppercase">On this page</p>
            <ol className="grid gap-1 text-[14px] sm:grid-cols-2">
              {headings.map((h) => (
                <li key={h.id}>
                  <a href={`#${h.id}`}>{h.text.replace(/\*\*/g, "")}</a>
                </li>
              ))}
            </ol>
          </nav>
        ) : null}
        <article className="legal" dangerouslySetInnerHTML={{ __html: html }} />
      </main>
    </PageShell>
  );
} // prettier-ignore
