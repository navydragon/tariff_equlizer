import { escapeHtml } from "./dom.js";

const VARIANTS = {
  success: {
    headerClass: "bg-success text-white",
    icon: "ti-check",
    title: "Успешно",
    closeWhite: true,
  },
  error: {
    headerClass: "bg-danger text-white",
    icon: "ti-alert-circle",
    title: "Ошибка",
    closeWhite: true,
  },
  warning: {
    headerClass: "bg-warning text-dark",
    icon: "ti-alert-triangle",
    title: "Внимание",
    closeWhite: false,
  },
  info: {
    headerClass: "bg-azure text-white",
    icon: "ti-info-circle",
    title: "Информация",
    closeWhite: true,
  },
};

function resolveContainer(container) {
  if (container instanceof HTMLElement) {
    return container;
  }
  if (typeof container === "string") {
    return document.querySelector(container);
  }
  return (
    document.getElementById("appToastContainer") ||
    document.querySelector("[data-toast-container]")
  );
}

function ensureContainer(container) {
  let el = resolveContainer(container);
  if (el) {
    return el;
  }

  el = document.createElement("div");
  el.id = "appToastContainer";
  el.className = "toast-container position-fixed bottom-0 end-0 p-3";
  el.style.zIndex = "1090";
  el.setAttribute("data-toast-container", "");
  document.body.appendChild(el);
  return el;
}

/**
 * @param {string|string[]} message
 * @param {{ variant?: 'success'|'error'|'warning'|'info', title?: string, delay?: number, container?: HTMLElement|string }} options
 */
export function showToast(message, options = {}) {
  if (typeof bootstrap === "undefined") {
    console.warn("[toast] Bootstrap is not available");
    if (Array.isArray(message)) {
      console.warn(message.join("\n"));
    } else {
      console.warn(message);
    }
    return null;
  }

  const messages = (Array.isArray(message) ? message : [message]).filter(Boolean);
  if (!messages.length) {
    return null;
  }

  const variant = options.variant || "info";
  const config = VARIANTS[variant] || VARIANTS.info;
  const container = ensureContainer(options.container);
  const delay = options.delay ?? (variant === "error" ? 8000 : 6000);
  const title = options.title || config.title;
  const closeClass = config.closeWhite ? "btn-close-white" : "";

  const toastEl = document.createElement("div");
  toastEl.className = "toast mb-2";
  toastEl.setAttribute("role", "alert");
  toastEl.setAttribute("aria-live", "assertive");
  toastEl.setAttribute("aria-atomic", "true");

  const bodyHtml = messages.map((line) => escapeHtml(String(line))).join("<br>");

  toastEl.innerHTML = `
    <div class="toast-header ${config.headerClass}">
      <i class="ti ${config.icon} me-2"></i>
      <strong class="me-auto">${escapeHtml(title)}</strong>
      <button type="button" class="btn-close ${closeClass}" data-bs-dismiss="toast" aria-label="Закрыть"></button>
    </div>
    <div class="toast-body">${bodyHtml}</div>
  `;

  container.appendChild(toastEl);

  const toast = bootstrap.Toast.getOrCreateInstance(toastEl, {
    autohide: true,
    delay,
  });

  toastEl.addEventListener("hidden.bs.toast", () => {
    toastEl.remove();
  });

  toast.show();
  return toast;
}

export function clearToasts(container) {
  if (typeof bootstrap === "undefined") {
    return;
  }

  const el = resolveContainer(container);
  if (!el) {
    return;
  }

  el.querySelectorAll(".toast").forEach((toastEl) => {
    const instance = bootstrap.Toast.getInstance(toastEl);
    if (instance) {
      instance.hide();
    } else {
      toastEl.remove();
    }
  });
}
