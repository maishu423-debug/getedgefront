"use client";

import { useRouter } from "next/navigation";
import { useId, useMemo, useState } from "react";

import { type Searchable, searchStations } from "@/lib/search";

export function StationSearch({
  stations,
  size = "lg",
}: {
  stations: Searchable[];
  size?: "lg" | "sm";
}) {
  const router = useRouter();
  const id = useId();
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const [open, setOpen] = useState(false);
  const results = useMemo(() => searchStations(stations, q), [stations, q]);
  const listId = `${id}-list`;
  const big = size === "lg";

  const go = (sid: string) => {
    setOpen(false);
    router.push(`/station/${sid}`);
  };

  return (
    <form
      role="search"
      className={`relative flex gap-2.5 ${big ? "max-w-[760px]" : "w-full max-w-[520px]"}`}
      onSubmit={(e) => {
        e.preventDefault();
        const pick = results[active] ?? results[0];
        if (pick) go(pick.id);
        else setOpen(true);
      }}
    >
      <label htmlFor={`${id}-q`} className="sr-only">
        Search stations
      </label>
      <div className="relative flex-1">
        <svg
          width="18"
          height="18"
          viewBox="0 0 24 24"
          aria-hidden
          fill="none"
          stroke="#56625F"
          strokeWidth="2"
          className={`absolute left-4 ${big ? "top-[17px]" : "top-3"}`}
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-4-4" />
        </svg>
        <input
          id={`${id}-q`}
          type="search"
          role="combobox"
          aria-expanded={open && q.trim() !== ""}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={
            open && results[active] ? `${id}-opt-${results[active]!.id}` : undefined
          }
          autoComplete="off"
          value={q}
          placeholder={
            big
              ? "Search a city, station code or nickname — e.g. Austin, KMDW, NYC"
              : "Search station or city — e.g. KDFW, Dallas"
          }
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setTimeout(() => setOpen(false), 150)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((a) => Math.min(a + 1, Math.max(results.length - 1, 0)));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
          className={`w-full rounded-[12px] border-[1.5px] border-[#CFD5D1] bg-[#F7F8F6] pr-4 pl-[46px] text-ink placeholder:text-muted-2 focus:border-brand focus:outline-none focus-visible:ring-2 focus-visible:ring-brand/40 ${
            big ? "h-[52px] text-[15.5px]" : "h-[42px] text-sm"
          }`}
        />
        {open && q.trim() !== "" ? (
          <ul
            id={listId}
            role="listbox"
            aria-label="Matching stations"
            className="absolute top-full right-0 left-0 z-30 mt-1.5 max-h-80 overflow-auto rounded-[12px] border border-border bg-surface py-1 shadow-lg"
          >
            {results.length === 0 ? (
              <li
                role="option"
                aria-selected={false}
                aria-disabled
                className="px-4 py-3 text-sm text-muted"
              >
                No station matches “{q.trim()}”. Try a city, a code like KDFW, or a nickname like
                NYC.
              </li>
            ) : (
              results.map((s, i) => (
                <li
                  key={s.id}
                  id={`${id}-opt-${s.id}`}
                  role="option"
                  aria-selected={i === active}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    go(s.id);
                  }}
                  onMouseEnter={() => setActive(i)}
                  className={`flex min-h-10 cursor-pointer items-center gap-3 px-4 py-2 text-sm ${
                    i === active ? "bg-brand-tint" : ""
                  }`}
                >
                  <span className="font-mono font-semibold text-brand">{s.id}</span>
                  <span className="text-text-2">{s.name}</span>
                </li>
              ))
            )}
          </ul>
        ) : null}
      </div>
      {big ? (
        <button
          type="submit"
          className="h-[52px] min-w-24 cursor-pointer rounded-[12px] bg-brand px-[22px] text-[15px] font-semibold text-white hover:bg-brand-hover focus-visible:ring-2 focus-visible:ring-brand/40 focus-visible:ring-offset-2 focus-visible:outline-none"
        >
          Search
        </button>
      ) : null}
    </form>
  );
}
