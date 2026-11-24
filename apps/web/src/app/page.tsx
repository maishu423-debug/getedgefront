import { connection } from "next/server";
import { Suspense } from "react";

import { fetchHealth } from "@/lib/api";
import { formatZulu } from "@/lib/time";

/** Temporary Phase 0 page: proves web → api → db wiring. Replaced in Phase 4. */
export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-(--container-content) flex-1 flex-col justify-center gap-6 px-4 py-16 sm:px-8">
      <div className="flex items-center gap-3">
        <svg width="34" height="22" viewBox="0 0 34 22" aria-hidden="true">
          <path
            d="M1 17 C9 17 11 7 17 7 S25 17 33 17"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.4"
            strokeLinecap="round"
            className="text-brand"
          />
          <path
            d="M7 14.6 L10.6 10.2 L12.4 15.2 Z M15.2 7.4 L19.4 3.6 L19.8 8.6 Z M23.4 11.2 L28 8.8 L26.8 14 Z"
            className="fill-brand"
          />
        </svg>
        <span className="font-display text-xl font-bold tracking-tight">EdgeFront</span>
      </div>
      <h1 className="max-w-3xl font-display text-4xl leading-tight font-bold tracking-tight sm:text-5xl">
        EdgeFront — coming soon
      </h1>
      <p className="max-w-2xl text-lg text-text-2">
        Observed weather at the U.S. stations weather markets settle on, each value with its source
        and time stamp.
      </p>
      <Suspense fallback={<p className="font-mono text-sm text-muted-2">Checking API status…</p>}>
        <ApiStatus />
      </Suspense>
    </main>
  );
}

async function ApiStatus() {
  await connection(); // request time only: never fetch the API during the build
  const result = await fetchHealth();

  if (!result.reachable) {
    return <StatusLine tone="down" label="API unreachable" detail={`(${result.error})`} />;
  }
  const { health } = result;
  if (health.status === "ok") {
    return (
      <StatusLine
        tone="ok"
        label="API ok · database ok"
        detail={`checked ${formatZulu(health.generated_at)}`}
      />
    );
  }
  return (
    <StatusLine
      tone="down"
      label={`API up · database ${health.db}`}
      detail={`checked ${formatZulu(health.generated_at)}`}
    />
  );
}

function StatusLine({
  tone,
  label,
  detail,
}: {
  tone: "ok" | "down";
  label: string;
  detail: string;
}) {
  return (
    <p className="flex items-center gap-2.5 font-mono text-sm text-text-2" role="status">
      <span
        aria-hidden="true"
        className={
          tone === "ok"
            ? "size-2.5 rounded-full bg-fresh ring-4 ring-fresh-halo"
            : "size-2.5 rounded-full bg-warn ring-4 ring-warn-halo"
        }
      />
      <span className="font-semibold">{label}</span>
      <span className="text-muted-2">{detail}</span>
    </p>
  );
}
