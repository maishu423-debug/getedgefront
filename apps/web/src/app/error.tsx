"use client";

import Link from "next/link";

export default function ErrorPage({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main
      id="main"
      className="mx-auto flex w-full max-w-[760px] flex-col gap-4 px-4 pt-14 pb-20 sm:px-8"
    >
      <h1 className="font-display text-[32px] font-bold">Something went wrong loading this page</h1>
      <p className="text-text-2">
        The data source may be temporarily unavailable. No data is shown rather than guessed.
      </p>
      <div className="flex gap-3">
        <button
          type="button"
          onClick={reset}
          className="min-h-10 cursor-pointer rounded-[9px] bg-brand px-4 text-sm font-semibold text-white hover:bg-brand-hover"
        >
          Try again
        </button>
        <Link href="/" className="inline-flex min-h-10 items-center">
          Go to the station board
        </Link>
      </div>
    </main>
  );
}
