/**
 * The small Markdown subset the legal documents use (v2 Part 2), rendered to HTML on the server
 * at build time: "#"/"##" headings (with anchor ids), paragraphs, "- " and "1. " lists, tables,
 * **bold**, `code`, [links](url) and "\*". Text is escaped first; the documents are our own files,
 * never user input. Leftover "[OWNER: …]" / "[VERIFY: …]" placeholders are highlighted.
 */

export interface Heading {
  id: string;
  text: string;
}

const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function slug(text: string): string {
  return text
    .toLowerCase()
    .replace(/[*`]/g, "")
    .replace(/&[a-z]+;/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function inline(raw: string): string {
  let s = esc(raw).replace(/\\\*/g, "&#42;");
  s = s.replace(/\[((?:OWNER|VERIFY):[^\]]*)\]/g, '<mark class="legal-todo">[$1]</mark>');
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_m, text: string, href: string) => {
    const ext = /^https?:\/\//.test(href);
    return `<a href="${href}"${ext ? ' rel="noopener noreferrer"' : ""}>${text}</a>`;
  });
  return s;
}

export function renderLegal(md: string): {
  title: string;
  /** the "**Effective date:** …" line, shown right under the title */
  effective: string;
  html: string;
  headings: Heading[];
} {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out: string[] = [];
  const headings: Heading[] = [];
  let title = "";
  let effective = "";
  let i = 0;
  const para: string[] = [];
  const flush = () => {
    if (para.length) out.push(`<p>${para.map(inline).join("<br />")}</p>`);
    para.length = 0;
  };
  while (i < lines.length) {
    const line = lines[i]!;
    if (!line.trim()) {
      flush();
      i++;
      continue;
    }
    const h = /^(#{1,3}) (.+)$/.exec(line);
    if (h) {
      flush();
      const level = h[1]!.length;
      const text = h[2]!;
      if (level === 1) {
        title = text;
      } else {
        const id = slug(text);
        headings.push({ id, text });
        out.push(
          `<h${level} id="${id}"><a class="legal-anchor" href="#${id}" aria-label="Link to this section">#</a>${inline(text)}</h${level}>`,
        );
      }
      i++;
      continue;
    }
    if (/^\s*[-*] /.test(line) || /^\s*\d+\. /.test(line)) {
      flush();
      const ordered = /^\s*\d+\. /.test(line);
      const items: string[] = [];
      while (
        i < lines.length &&
        (ordered ? /^\s*\d+\. /.test(lines[i]!) : /^\s*[-*] /.test(lines[i]!))
      ) {
        items.push(`<li>${inline(lines[i]!.replace(/^\s*(?:[-*]|\d+\.) /, ""))}</li>`);
        i++;
      }
      out.push(`<${ordered ? "ol" : "ul"}>${items.join("")}</${ordered ? "ol" : "ul"}>`);
      continue;
    }
    if (line.startsWith("|")) {
      flush();
      const rows: string[][] = [];
      while (i < lines.length && lines[i]!.startsWith("|")) {
        rows.push(
          lines[i]!.replace(/^\||\|$/g, "")
            .split("|")
            .map((c) => c.trim()),
        );
        i++;
      }
      const [head, , ...body] = rows;
      out.push(
        `<div class="legal-table" role="region" tabindex="0" aria-label="Table"><table><thead><tr>${(head ?? []).map((c) => `<th scope="col">${inline(c)}</th>`).join("")}</tr></thead><tbody>${body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`,
      );
      continue;
    }
    if (!effective && /^\*\*Effective date:\*\*/.test(line)) {
      effective = inline(line);
      i++;
      continue;
    }
    para.push(line);
    i++;
  }
  flush();
  return { title, effective, html: out.join("\n"), headings };
}
