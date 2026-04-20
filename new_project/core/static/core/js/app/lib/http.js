// Простые обертки вокруг fetch для JSON-запросов.

export async function fetchJson(url, options = {}) {
  const { method = "GET", body, csrf = true, headers = {} } = options;

  const finalHeaders = {
    "Accept": "application/json",
    ...headers,
  };

  let finalBody = body;
  if (body && typeof body === "object" && !(body instanceof FormData)) {
    finalHeaders["Content-Type"] =
      finalHeaders["Content-Type"] || "application/json";
    finalBody = JSON.stringify(body);
  }

  if (csrf) {
    const token = getCookie("csrftoken");
    if (token) {
      finalHeaders["X-CSRFToken"] = token;
    }
  }

  const response = await fetch(url, {
    method,
    headers: finalHeaders,
    body: finalBody,
  });

  const data = await response.json().catch(() => null);
  return { response, data };
}

export function getCookie(name) {
  let cookieValue = null;
  if (document.cookie && document.cookie !== "") {
    const cookies = document.cookie.split(";");
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === name + "=") {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

