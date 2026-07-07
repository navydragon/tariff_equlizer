import { fetchJson } from "./http.js";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function cacheReadinessMessage(status) {
  if (!status) {
    return "Обновление данных…";
  }
  if (status.message) {
    return String(status.message);
  }
  if (status.mart_phase === "queued" || status.mart_phase === "building") {
    return "Пересборка витрины маршрутов…";
  }
  if (status.scenario_phase === "mask") {
    return "Пересборка масок сценария…";
  }
  if (status.scenario_phase === "kpi") {
    return "Обновление итогов сценария…";
  }
  if (status.scenario_phase === "compact") {
    return "Детализация в фоне…";
  }
  if (status.scenario_phase === "done") {
    return "Пересчёт завершён";
  }
  return "Обновление данных…";
}

export function cacheReadinessVariant(status) {
  return status && (status.mart_phase === "error" || status.scenario_phase === "error")
    ? "danger"
    : "info";
}

export async function pollCacheReadiness({
  scenarioId,
  cacheReadinessUrl,
  onStatus,
  timeoutMs = 120000,
  intervalMs = 300,
}) {
  if (!scenarioId || !cacheReadinessUrl) {
    return null;
  }

  const startedAt = Date.now();
  while (Date.now() - startedAt <= timeoutMs) {
    try {
      const url =
        `${cacheReadinessUrl}?scenario_id=` +
        encodeURIComponent(String(scenarioId));
      const { data } = await fetchJson(url);
      if (data && data.success) {
        if (onStatus) {
          onStatus(data);
        }
        if (data.ready_for_compute || (!data.mart_phase && !data.scenario_phase)) {
          return data;
        }
        if (data.mart_phase === "error" || data.scenario_phase === "error") {
          return data;
        }
      }
    } catch (error) {
      console.error("[cache-readiness] poll failed", error);
    }
    await sleep(intervalMs);
  }
  return null;
}
