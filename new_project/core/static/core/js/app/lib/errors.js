// Утилиты отображения ошибок в унифицированном формате.

import { escapeHtml } from "./dom.js";

export function renderErrors(container, errors) {
  if (!container) return;
  const list = Array.isArray(errors) ? errors : [errors];

  if (!list.length) {
    container.innerHTML = "";
    return;
  }

  const html =
    '<div class="alert alert-danger"><ul class="mb-0">' +
    list.map((e) => `<li>${escapeHtml(String(e))}</li>`).join("") +
    "</ul></div>";

  container.innerHTML = html;
}

