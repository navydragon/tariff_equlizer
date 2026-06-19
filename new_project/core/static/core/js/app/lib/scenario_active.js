import { fetchJson } from "./http.js";

export function setActiveScenarioUrl(scenarioId) {
  return `/scenarios/api/${scenarioId}/set-active/`;
}

export async function persistActiveScenario(scenarioId, options = {}) {
  const { routeSetId = null, onError } = options;
  if (!scenarioId) return false;

  const { response, data } = await fetchJson(setActiveScenarioUrl(scenarioId), {
    method: "POST",
  });

  if (!response.ok || !data || !data.success) {
    const errors = (data && data.errors) || ["Не удалось сохранить активный сценарий"];
    if (onError) onError(errors);
    return false;
  }

  document.dispatchEvent(
    new CustomEvent("scenario:active-changed", {
      bubbles: true,
      detail: {
        scenarioId: Number(scenarioId),
        routeSetId:
          routeSetId != null && !Number.isNaN(Number(routeSetId))
            ? Number(routeSetId)
            : null,
      },
    }),
  );

  return true;
}
