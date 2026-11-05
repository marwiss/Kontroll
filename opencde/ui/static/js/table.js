// Table enhancements: a filter box for tables marked data-filterable and
// click-to-sort headers for tables marked data-sortable. Everything is built
// with DOM APIs (no innerHTML); the table works unchanged without this script.

function rowsOf(table) {
  return Array.from(table.tBodies[0]?.rows ?? []);
}

function addFilter(table) {
  const wrap = table.closest(".table-wrap") ?? table;
  const label = document.createElement("label");
  label.className = "table-tools";
  const text = document.createElement("span");
  text.className = "sr-only";
  text.textContent = "Filter rows";
  const input = document.createElement("input");
  input.type = "search";
  input.className = "input";
  input.placeholder = "Filter rows…";
  input.setAttribute("aria-controls", table.id || (table.id = `table-${Math.random().toString(36).slice(2, 8)}`));
  label.append(text, input);
  wrap.parentNode.insertBefore(label, wrap);

  const status = document.createElement("p");
  status.className = "muted table-tools__status";
  status.setAttribute("role", "status");
  wrap.parentNode.insertBefore(status, wrap.nextSibling);

  input.addEventListener("input", () => {
    const needle = input.value.trim().toLowerCase();
    let shown = 0;
    for (const row of rowsOf(table)) {
      const match = !needle || row.textContent.toLowerCase().includes(needle);
      row.hidden = !match;
      if (match) shown += 1;
    }
    status.textContent = needle ? `${shown} of ${rowsOf(table).length} rows match` : "";
  });
}

function addSorting(table) {
  const headers = Array.from(table.tHead?.rows[0]?.cells ?? []);
  headers.forEach((header, index) => {
    const label = header.textContent.trim();
    if (!label) return;
    // A real button inside the header keeps the cell a column header (aria-sort is only valid there).
    header.setAttribute("aria-sort", "none");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "table__sort";
    button.textContent = label;
    header.replaceChildren(button);
    button.addEventListener("click", () => {
      const ascending = header.getAttribute("aria-sort") !== "ascending";
      headers.forEach((other) => other !== header && other.hasAttribute("aria-sort") && other.setAttribute("aria-sort", "none"));
      header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
      const body = table.tBodies[0];
      const sorted = rowsOf(table).sort((a, b) => {
        const left = a.cells[index]?.textContent.trim() ?? "";
        const right = b.cells[index]?.textContent.trim() ?? "";
        const numeric = Number(left) - Number(right);
        const result = Number.isNaN(numeric) ? left.localeCompare(right, undefined, { sensitivity: "base" }) : numeric;
        return ascending ? result : -result;
      });
      sorted.forEach((row) => body.appendChild(row));
    });
  });
}

export function enhanceTables(root = document) {
  root.querySelectorAll("table[data-filterable]").forEach((table) => rowsOf(table).length > 5 && addFilter(table));
  root.querySelectorAll("table[data-sortable]").forEach(addSorting);
}
