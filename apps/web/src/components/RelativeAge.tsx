"use client";

import { useNow } from "@/lib/hooks";
import { relativeAge } from "@/lib/time";

/** "12 min ago", rendered only after mount (the server renders nothing → no hydration mismatch). */
export function RelativeAge({
  iso,
  prefix = "",
}: {
  iso: string | null | undefined;
  prefix?: string;
}) {
  const now = useNow();
  if (now === null || !iso) return null;
  return (
    <span suppressHydrationWarning>
      {prefix}
      {relativeAge(iso, now)}
    </span>
  );
}
