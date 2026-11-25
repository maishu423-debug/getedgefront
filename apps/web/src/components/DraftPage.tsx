import { PageShell } from "./Chrome";

/** Placeholder for legal pages. Owner rule: no legal text is written here. */
export function DraftPage({ title }: { title: string }) {
  return (
    <PageShell>
      <main
        id="main"
        className="mx-auto flex w-full max-w-[760px] flex-col gap-4 px-4 pt-10 pb-16 sm:px-8"
      >
        <h1 className="font-display text-[36px] font-bold tracking-[-0.02em]">{title}</h1>
        <p
          role="note"
          className="rounded-[10px] border border-[#F0DDB8] bg-[#FFF7E8] px-4 py-3 text-sm font-semibold text-[#6B4600]"
        >
          Draft — pending legal review
        </p>
        <p className="text-text-2">
          This page has not been written yet. It will be published here after legal review.
        </p>
      </main>
    </PageShell>
  );
}
