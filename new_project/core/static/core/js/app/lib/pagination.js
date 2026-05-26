// Утилита для отрисовки пагинации Tabler/Bootstrap.

export function renderPagination(container, { page, totalPages, onPage }) {
  if (!container) return;

  const current = page || 1;
  const total = totalPages || 1;
  container.innerHTML = "";

  function createItem(label, targetPage, disabled, active) {
    const li = document.createElement("li");
    li.className = "page-item";
    if (disabled) li.classList.add("disabled");
    if (active) li.classList.add("active");

    const a = document.createElement("a");
    a.className = "page-link";
    a.href = "#";
    a.textContent = label;
    if (!disabled && typeof targetPage === "number") {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (targetPage !== current && onPage) {
          onPage(targetPage);
        }
      });
    }

    li.appendChild(a);
    container.appendChild(li);
  }

  createItem("‹", current - 1, current <= 1, false);

  const maxButtons = 5;
  let start = Math.max(1, current - Math.floor(maxButtons / 2));
  let end = start + maxButtons - 1;
  if (end > total) {
    end = total;
    start = Math.max(1, end - maxButtons + 1);
  }

  for (let p = start; p <= end; p++) {
    createItem(String(p), p, false, p === current);
  }

  createItem("›", current + 1, current >= total, false);
}

/** Пагинация без COUNT(*) — только «назад» / «вперёд». */
export function renderPaginationHasNext(container, { page, hasNext, onPage }) {
  if (!container) return;

  const current = page || 1;
  container.innerHTML = "";

  function createItem(label, targetPage, disabled) {
    const li = document.createElement("li");
    li.className = "page-item";
    if (disabled) li.classList.add("disabled");

    const a = document.createElement("a");
    a.className = "page-link";
    a.href = "#";
    a.textContent = label;
    if (!disabled && typeof targetPage === "number") {
      a.addEventListener("click", (e) => {
        e.preventDefault();
        if (targetPage !== current && onPage) {
          onPage(targetPage);
        }
      });
    }

    li.appendChild(a);
    container.appendChild(li);
  }

  createItem("‹", current - 1, current <= 1);
  createItem("›", current + 1, !hasNext);
}

if (typeof window !== "undefined") {
  window.renderPagination = renderPagination;
  window.renderPaginationHasNext = renderPaginationHasNext;
}
