/** Client-side station search over codes, names, cities and aliases (stations.yaml). */

export interface Searchable {
  id: string;
  name: string;
  city: string;
  state: string;
  aliases: string[];
}

function norm(s: string): string {
  return s
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

/** Lower score = better. null = no match. */
function score(st: Searchable, q: string): number | null {
  const code = st.id.toLowerCase();
  const short = code.replace(/^k/, "");
  if (q === code || q === short) return 0;
  const aliases = st.aliases.map(norm);
  if (aliases.includes(q)) return 1;
  if (code.startsWith(q) || short.startsWith(q)) return 2;
  const words = [norm(st.city), norm(st.name), ...aliases];
  if (words.some((w) => w.startsWith(q))) return 3;
  if (words.some((w) => w.split(" ").some((t) => t.startsWith(q)))) return 4;
  if (words.some((w) => w.includes(q))) return 5;
  return null;
}

export function searchStations<T extends Searchable>(stations: T[], query: string, limit = 8): T[] {
  const q = norm(query);
  if (!q) return [];
  return stations
    .map((s) => ({ s, sc: score(s, q) }))
    .filter((x): x is { s: T; sc: number } => x.sc !== null)
    .sort((a, b) => a.sc - b.sc || a.s.id.localeCompare(b.s.id))
    .slice(0, limit)
    .map((x) => x.s);
}
