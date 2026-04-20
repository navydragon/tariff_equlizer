// DOM утилиты, общие для контроллеров.

export function escapeHtml(text) {
  if (text == null) return "";
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

export function setVisible(element, visible) {
  if (!element) return;
  element.style.display = visible ? "" : "none";
}

