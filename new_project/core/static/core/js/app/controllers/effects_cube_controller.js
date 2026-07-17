import { fetchBlob, fetchJson } from "../lib/http.js";
import {
  cacheReadinessMessage,
  cacheReadinessVariant,
  pollCacheReadiness,
} from "../lib/cache_readiness.js";
import { escapeHtml } from "../lib/dom.js";
import { persistActiveScenario } from "../lib/scenario_active.js";
import { clearToasts, showToast } from "../lib/toast.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus is not available for effects-cube.");
    return;
  }

  class EffectsCubeController extends Stimulus.Controller {
    static targets = [
      "scenarioSelect",
      "groupBySelect",
      "groupByInnerSelect",
      "cargoFilterSelect",
      "holdingFilterSelect",
      "tableWrap",
      "toastContainer",
      "rebuildStatus",
    ];

    static values = {
      scenariosUrl: String,
      computeUrl: String,
      computePandasUrl: String,
      cacheReadinessUrl: String,
      warmStatusUrl: String,
      compactStatusUrl: String,
      cubeUrl: String,
      cubeStartUrl: String,
      cubeStatusUrl: String,
      exportUrl: String,
      activeScenarioId: String,
      debounceMs: { type: Number, default: 350 },
    };

    connect() {
      this.state = {
        scenarioById: new Map(),
        selectedScenarioId: null,
        cacheKey: null,
        scenarioYears: [],
        cargoTomSelect: null,
        holdingTomSelect: null,
        cubeTimer: null,
        loadProgressTimer: null,
        loadProgressToken: 0,
        loadProgressStartedAt: 0,
        suppressFilterEvents: false,
        computing: false,
        compactPending: false,
        groupByInnerLabel: null,
        groupByLabel: "Группа груза",
        lastCubeJobId: null,
        lastCubePayloadKey: null,
        exporting: false,
      };

      this._onScenarioRecalculated = this._onScenarioRecalculated.bind(this);
      this._onScenarioEditMessage = this._onScenarioEditMessage.bind(this);
      document.addEventListener("scenario-recalculated", this._onScenarioRecalculated);
      window.addEventListener("message", this._onScenarioEditMessage);

      this.state.routeMartRebuildModalEl = document.getElementById(
        "routeMartRebuildModal",
      );
      this.state.routeMartRebuildMessageEl = document.getElementById(
        "routeMartRebuildMessage",
      );
      if (
        this.state.routeMartRebuildModalEl &&
        typeof bootstrap !== "undefined"
      ) {
        this.state.routeMartRebuildModal =
          bootstrap.Modal.getOrCreateInstance(
            this.state.routeMartRebuildModalEl,
            { backdrop: "static", keyboard: false },
          );
      } else {
        this.state.routeMartRebuildModal = null;
      }

      this._loadScenarios();
    }

    disconnect() {
      document.removeEventListener("scenario-recalculated", this._onScenarioRecalculated);
      window.removeEventListener("message", this._onScenarioEditMessage);
      this._stopCubeLoadProgress();
      this._destroyTomSelects();
    }

    onScenarioChange() {
      const raw = this.hasScenarioSelectTarget
        ? this.scenarioSelectTarget.value
        : "";
      const scenarioId = raw ? Number(raw) : null;
      this.state.selectedScenarioId = scenarioId;
      this.state.cacheKey = null;
      this._persistActiveScenario(scenarioId);
      this._computeEffects();
    }

    onFilterChange() {
      if (this.state.suppressFilterEvents) return;

      this._syncTariffDecisionMode();

      if (
        this.hasGroupBySelectTarget &&
        this.hasGroupByInnerSelectTarget &&
        this.groupByInnerSelectTarget.value !== "none" &&
        this.groupByInnerSelectTarget.value === this.groupBySelectTarget.value
      ) {
        this.groupByInnerSelectTarget.value = "none";
      }

      if (!this.state.cacheKey) {
        this._computeEffects();
        return;
      }

      clearTimeout(this.state.cubeTimer);
      this.state.cubeTimer = setTimeout(() => {
        this._aggregateCube({ showTableLoading: true });
      }, this.debounceMsValue || 350);
    }

    onExport() {
      if (this.state.exporting) {
        return;
      }
      this._exportCube();
    }

    _syncTariffDecisionMode() {
      if (!this.hasGroupBySelectTarget || !this.hasGroupByInnerSelectTarget) {
        return;
      }

      const isTariffDecision =
        this.groupBySelectTarget.value === "tariff_decision";
      this.groupByInnerSelectTarget.disabled = isTariffDecision;
      if (isTariffDecision) {
        this.groupByInnerSelectTarget.value = "none";
      }
    }

    async _loadScenarios() {
      if (!this.scenariosUrlValue) return;

      const { data } = await fetchJson(this.scenariosUrlValue);
      if (!data || !data.success) {
        this._showError(
          (data && data.errors && data.errors.join("; ")) ||
            "Не удалось загрузить сценарии",
        );
        return;
      }

      const scenarios = data.scenarios || [];
      this.state.scenarioById = new Map(
        scenarios.map((item) => [Number(item.id), item]),
      );

      if (!this.hasScenarioSelectTarget) return;

      this.scenarioSelectTarget.innerHTML = "";
      if (!scenarios.length) {
        const opt = document.createElement("option");
        opt.value = "";
        opt.textContent = "Нет доступных сценариев";
        this.scenarioSelectTarget.appendChild(opt);
        return;
      }

      for (const scenario of scenarios) {
        const opt = document.createElement("option");
        opt.value = String(scenario.id);
        opt.textContent = scenario.name || `Сценарий #${scenario.id}`;
        this.scenarioSelectTarget.appendChild(opt);
      }

      const activeRaw = this.activeScenarioIdValue || "";
      const activeId = activeRaw ? Number(activeRaw) : null;
      const fallbackId = scenarios[0] ? Number(scenarios[0].id) : null;
      const selectedId =
        activeId && this.state.scenarioById.has(activeId)
          ? activeId
          : fallbackId;

      if (selectedId) {
        this.scenarioSelectTarget.value = String(selectedId);
        this.state.selectedScenarioId = selectedId;
        this._computeEffects();
      }
    }

    _resolveComputeUrl() {
      return this.computePandasUrlValue || this.computeUrlValue;
    }

    _onScenarioRecalculated(event) {
      const scenarioId = event?.detail?.scenarioId;
      if (
        scenarioId &&
        this.state.selectedScenarioId &&
        Number(scenarioId) === Number(this.state.selectedScenarioId)
      ) {
        this._handleScenarioRecalculated();
      }
    }

    _onScenarioEditMessage(event) {
      if (event.origin !== window.location.origin) return;
      if (!event.data || event.data.type !== "scenario-recalculated") return;
      this._onScenarioRecalculated({ detail: { scenarioId: event.data.scenarioId } });
    }

    async _handleScenarioRecalculated() {
      if (this.state.computing) {
        return;
      }
      this.state.cacheKey = null;
      await this._waitForWarmKpi(this.state.selectedScenarioId);
      await this._computeEffects();
    }

    async _waitForWarmKpi(scenarioId, startedAt = Date.now()) {
      if (!this.hasWarmStatusUrlValue || !scenarioId) {
        return;
      }
      const timeoutMs = 120000;
      if (Date.now() - startedAt > timeoutMs) {
        return;
      }

      const url = `${this.warmStatusUrlValue}?scenario_id=${encodeURIComponent(
        String(scenarioId),
      )}`;
      try {
        const { data } = await fetchJson(url);
        if (!data || !data.success || !data.phase) {
          return;
        }
        if (data.phase === "error") {
          console.error("[effects-cube] scenario warm failed", data.error);
          return;
        }
        this._setTableLoading(
          true,
          this._progressMessage(data.message || "Подготовка данных…", data.progress_pct),
          data.progress_pct,
        );
        if (data.kpi_ready || data.phase === "done") {
          return;
        }
        await this._sleep(400);
        return this._waitForWarmKpi(scenarioId, startedAt);
      } catch (error) {
        console.error("[effects-cube] warm status poll failed", error);
        await this._sleep(500);
        return this._waitForWarmKpi(scenarioId, startedAt);
      }
    }

    _sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    _isCubePendingMessage(message) {
      return (
        typeof message === "string" &&
        (message.includes("ещё выполняется") ||
          message.includes("еще выполняется"))
      );
    }

    async _waitForCompactReady() {
      if (!this.compactStatusUrlValue || !this.state.cacheKey) {
        await this._sleep(400);
        return;
      }

      try {
        const { data } = await fetchJson(this.compactStatusUrlValue, {
          method: "POST",
          body: { cache_key: this.state.cacheKey },
        });
        if (data && data.success) {
          this.state.compactPending = !data.compact_ready;
          if (!data.compact_ready) {
            this._setTableLoading(
              true,
              this._progressMessage(
                data.message || this._cubeLoadingMessage(),
                data.progress_pct,
              ),
              data.progress_pct,
            );
          }
        }
      } catch (error) {
        console.error("[effects-cube] compact-status failed", error);
      }
      await this._sleep(400);
    }

    _progressMessage(message, progressPct) {
      if (typeof progressPct === "number" && Number.isFinite(progressPct)) {
        const pct = Math.max(0, Math.min(100, Math.round(progressPct)));
        return `${message} ${pct}%`;
      }
      return message;
    }

    async _computeEffects() {
      const computeUrl = this._resolveComputeUrl();
      if (!computeUrl || !this.state.selectedScenarioId) return;

      this._clearToasts();
      const readiness = await this._waitForCacheReadiness(
        this.state.selectedScenarioId,
      );
      if (readiness && readiness.mart_phase === "error") {
        this.state.cacheKey = null;
        this._setTableMessage("—");
        this._showError(
          readiness.message || "Ошибка пересборки витрины маршрутов",
        );
        return;
      }
      if (
        readiness &&
        readiness.scenario_phase === "error" &&
        !readiness.error_recoverable &&
        !readiness.ready_for_compute &&
        !readiness.kpi_ready
      ) {
        this.state.cacheKey = null;
        this._setTableMessage("—");
        this._showError(readiness.message || "Ошибка пересчёта сценария");
        return;
      }
      if (
        readiness &&
        readiness.scenario_phase === "error" &&
        (readiness.error_recoverable ||
          readiness.ready_for_compute ||
          readiness.kpi_ready)
      ) {
        this._showRebuildStatus(
          readiness.message ||
            "Базовые данные готовы; разбивка по правилам может быть недоступна.",
          "danger",
        );
      }
      this._setTableLoading(true, "Расчёт данных…");
      this.state.computing = true;

      try {
        await this._waitForWarmKpi(this.state.selectedScenarioId);

        const { response, data } = await fetchJson(computeUrl, {
          method: "POST",
          body: {
            scenario_id: this.state.selectedScenarioId,
            include_rule_breakdown: true,
          },
        });

        if (!response.ok || !data || !data.success) {
          if (response.status === 409 && data && data.code === "mart_rebuilding") {
            this._hideRebuildStatus();
            this._showRouteMartRebuildModal(cacheReadinessMessage(data));
            const waited = await this._waitForCacheReadiness(
              this.state.selectedScenarioId,
            );
            if (!waited || waited.mart_phase === "error") {
              return;
            }
            if (
              waited.scenario_phase === "error" &&
              !waited.error_recoverable &&
              !waited.ready_for_compute &&
              !waited.kpi_ready
            ) {
              return;
            }
            return this._computeEffects();
          }
          this.state.cacheKey = null;
          this._setTableMessage("—");
          this._showError(
            (data && data.errors && data.errors.join("; ")) ||
              "Ошибка расчёта эффектов",
          );
          return;
        }

        this.state.cacheKey = data.cache_key || null;
        this.state.compactPending = data.compact_ready === false;
        this.state.scenarioYears = data.years || [];
        this._renderWarning(
          data.routes_without_charge,
          data.routes_without_volume,
          {
            engine: data.engine,
            elapsed_ms: data.elapsed_ms,
          },
        );
        this._syncFilterOptions(data.filter_options || {});
        await this._aggregateCube({ showTableLoading: true });
      } catch (error) {
        console.error("[effects-cube] compute failed", error);
        this.state.cacheKey = null;
        this._setTableMessage("—");
        this._showError(
          "Не удалось выполнить расчёт. Попробуйте обновить страницу.",
        );
      } finally {
        this.state.computing = false;
      }
    }

    _hideRebuildStatus() {
      if (!this.hasRebuildStatusTarget) return;
      this.rebuildStatusTarget.classList.add("d-none");
      this.rebuildStatusTarget.innerHTML = "";
    }

    _showRebuildStatus(message, variant = "info") {
      if (!this.hasRebuildStatusTarget) return;
      const alertClass =
        variant === "danger"
          ? "alert-danger"
          : variant === "success"
            ? "alert-success"
            : "alert-info";
      this.rebuildStatusTarget.classList.remove("d-none");
      this.rebuildStatusTarget.innerHTML = `
        <div class="alert ${alertClass} py-2 px-3 mb-3" role="status">
          ${
            variant === "danger" || variant === "success"
              ? ""
              : '<span class="spinner-border spinner-border-sm text-primary me-2" role="status"></span>'
          }
          ${escapeHtml(message)}
        </div>
      `;
    }

    _showRouteMartRebuildModal(message) {
      if (!this.state?.routeMartRebuildModal) return;
      if (this.state?.routeMartRebuildMessageEl) {
        this.state.routeMartRebuildMessageEl.textContent =
          message || "Пересборка витрины маршрутов";
      }
      this.state.routeMartRebuildModal.show();
    }

    _hideRouteMartRebuildModal() {
      if (!this.state?.routeMartRebuildModal) return;
      this.state.routeMartRebuildModal.hide();
    }

    async _waitForCacheReadiness(scenarioId) {
      if (!scenarioId || !this.cacheReadinessUrlValue) {
        return;
      }
      const status = await pollCacheReadiness({
        scenarioId,
        cacheReadinessUrl: this.cacheReadinessUrlValue,
        timeoutMs: 15 * 60 * 1000,
        onStatus: (payload) => {
          if (payload.mart_phase === "queued" || payload.mart_phase === "building") {
            this._hideRebuildStatus();
            this._showRouteMartRebuildModal(cacheReadinessMessage(payload));
            return;
          }

          if (
            payload.ready_for_compute ||
            (!payload.mart_phase && !payload.scenario_phase)
          ) {
            this._hideRebuildStatus();
            this._hideRouteMartRebuildModal();
            return;
          }

          this._hideRouteMartRebuildModal();
          this._showRebuildStatus(
            cacheReadinessMessage(payload),
            cacheReadinessVariant(payload),
          );
        },
      });
      if (
        status &&
        (status.ready_for_compute ||
          (!status.mart_phase && !status.scenario_phase))
      ) {
        this._hideRebuildStatus();
        this._hideRouteMartRebuildModal();
      } else if (
        status &&
        (status.mart_phase === "queued" || status.mart_phase === "building")
      ) {
        this._hideRebuildStatus();
        this._showRouteMartRebuildModal(cacheReadinessMessage(status));
      } else if (status) {
        this._showRebuildStatus(
          cacheReadinessMessage(status),
          cacheReadinessVariant(status),
        );
      } else {
        this._hideRouteMartRebuildModal();
        this._showRebuildStatus(
          "Пересборка витрины занимает больше ожидаемого времени. Попробуйте обновить страницу через пару минут.",
          "danger",
        );
      }
      return status;
    }

    _cubeLoadingMessage() {
      const groupBy = this.groupBySelectTarget?.value || "cargo_group";
      if (groupBy === "tariff_decision") {
        return this.state.compactPending
          ? "Подготовка разбивки по тарифным решениям…"
          : "Загрузка тарифных решений…";
      }
      return "Загрузка таблицы…";
    }

    _cubeLoadExpectedMs() {
      const groupBy = this.groupBySelectTarget?.value || "cargo_group";
      if (groupBy === "tariff_decision") {
        return this.state.compactPending ? 90000 : 45000;
      }
      return this.state.compactPending ? 60000 : 20000;
    }

    _estimatedLoadProgressPct() {
      const startedAt = this.state.loadProgressStartedAt || Date.now();
      const elapsed = Math.max(0, Date.now() - startedAt);
      const expected = this._cubeLoadExpectedMs();
      // Асимптота к 95%, пока сервер не ответит.
      const pct = 95 * (1 - Math.exp(-elapsed / expected));
      return Math.max(1, Math.min(95, Math.round(pct)));
    }

    _stopCubeLoadProgress() {
      this.state.loadProgressToken = (this.state.loadProgressToken || 0) + 1;
      if (this.state.loadProgressTimer) {
        clearInterval(this.state.loadProgressTimer);
        this.state.loadProgressTimer = null;
      }
    }

    _showCubeLoadProgress(progressPct = null, message = null) {
      const pct =
        typeof progressPct === "number" && Number.isFinite(progressPct)
          ? progressPct
          : this._estimatedLoadProgressPct();
      const baseMessage = message || this._cubeLoadingMessage();
      this._setTableLoading(
        true,
        this._progressMessage(baseMessage, pct),
        pct,
      );
    }

    async _pollCubeLoadProgress(token) {
      if (token !== this.state.loadProgressToken) {
        return;
      }

      let serverPct = null;
      let serverMessage = null;

      try {
        if (this.state.compactPending && this.compactStatusUrlValue && this.state.cacheKey) {
          const { data } = await fetchJson(this.compactStatusUrlValue, {
            method: "POST",
            body: { cache_key: this.state.cacheKey },
          });
          if (data && data.success) {
            this.state.compactPending = !data.compact_ready;
            if (typeof data.progress_pct === "number") {
              serverPct = data.progress_pct;
            }
            if (data.message) {
              serverMessage = data.message;
            }
          }
        } else if (this.hasWarmStatusUrlValue && this.state.selectedScenarioId) {
          const url = `${this.warmStatusUrlValue}?scenario_id=${encodeURIComponent(
            String(this.state.selectedScenarioId),
          )}`;
          const { data } = await fetchJson(url);
          if (
            data &&
            data.success &&
            data.phase &&
            data.phase !== "done" &&
            data.phase !== "error" &&
            typeof data.progress_pct === "number"
          ) {
            serverPct = data.progress_pct;
            serverMessage = data.message || null;
          }
        }
      } catch (error) {
        // Оценка по времени остаётся fallback.
      }

      if (token !== this.state.loadProgressToken) {
        return;
      }

      // Серверный % (warm/compact) смешиваем с оценкой загрузки таблицы,
      // чтобы «Тарифные решения» не зависали на одном значении после ready.
      let pct = this._estimatedLoadProgressPct();
      if (typeof serverPct === "number" && Number.isFinite(serverPct)) {
        pct = Math.max(pct, Math.min(95, Math.round(serverPct)));
      }
      this._showCubeLoadProgress(pct, serverMessage || this._cubeLoadingMessage());
    }

    _startCubeLoadProgress() {
      this._stopCubeLoadProgress();
      this.state.loadProgressStartedAt = Date.now();
      const token = this.state.loadProgressToken;
      this._showCubeLoadProgress(1);
      this.state.loadProgressTimer = setInterval(() => {
        this._pollCubeLoadProgress(token);
      }, 400);
      this._pollCubeLoadProgress(token);
    }

    async _aggregateCube({ showTableLoading = false, attempt = 0 } = {}) {
      if (!this.state.selectedScenarioId || !this.state.cacheKey) {
        return;
      }
      if (this.cubeStartUrlValue && this.cubeStatusUrlValue) {
        return this._aggregateCubeViaJob({ showTableLoading, attempt });
      }
      if (!this.cubeUrlValue) {
        return;
      }
      return this._aggregateCubeSync({ showTableLoading, attempt });
    }

    async _aggregateCubeViaJob({ showTableLoading = false, attempt = 0 } = {}) {
      if (showTableLoading || attempt > 0) {
        this._setTableLoading(
          true,
          this._progressMessage(this._cubeLoadingMessage(), 0),
          0,
        );
      }

      const maxAttempts = this.state.compactPending ? 45 : 8;

      try {
        if (this.state.compactPending && attempt + 1 <= maxAttempts) {
          await this._waitForCompactReady();
          if (this.state.compactPending) {
            return this._aggregateCubeViaJob({
              showTableLoading,
              attempt: attempt + 1,
            });
          }
        }

        const { response, data } = await fetchJson(this.cubeStartUrlValue, {
          method: "POST",
          body: this._cubePayload(),
        });

        if (!response.ok || !data || !data.success) {
          const message =
            (data && data.errors && data.errors.join("; ")) ||
            "Не удалось запустить агрегацию куба";
          if (
            !this.state.computing &&
            (message.includes("устарел") || message.includes("недоступен"))
          ) {
            this.state.cacheKey = null;
            this._computeEffects();
            return;
          }
          if (this._isCubePendingMessage(message) && attempt + 1 < maxAttempts) {
            await this._sleep(400);
            return this._aggregateCubeViaJob({
              showTableLoading,
              attempt: attempt + 1,
            });
          }
          this._setTableMessage("Нет данных.");
          this._showError(message);
          return;
        }

        const tableData = await this._pollCubeJobUntilDone(data.job_id);
        if (!tableData) {
          return;
        }

        this._rememberCubeResult(data.job_id, tableData);
        this.state.compactPending = false;
        this.state.groupByLabel = tableData.group_by_label || this.state.groupByLabel;
        this.state.groupByInnerLabel = tableData.group_by_inner_label;
        this._renderCubeTable(tableData);
      } catch (error) {
        console.error("[effects-cube] aggregate job failed", error);
        this._setTableMessage("Не удалось загрузить таблицу.");
        this._showError("Не удалось загрузить куб эффектов.");
      }
    }

    async _pollCubeJobUntilDone(jobId) {
      const timeoutMs = 180000;
      const startedAt = Date.now();

      while (Date.now() - startedAt < timeoutMs) {
        const { response, data } = await fetchJson(this.cubeStatusUrlValue, {
          method: "POST",
          body: { job_id: jobId },
        });

        if (!response.ok || !data || !data.success) {
          const message =
            (data && data.errors && data.errors.join("; ")) ||
            "Не удалось получить статус агрегации";
          this._setTableMessage("Нет данных.");
          this._showError(message);
          return null;
        }

        if (data.phase === "error") {
          this._setTableMessage("Нет данных.");
          this._showError(data.error || "Ошибка агрегации куба");
          return null;
        }

        const pct =
          typeof data.progress_pct === "number" ? data.progress_pct : null;
        this._setTableLoading(
          true,
          this._progressMessage(
            data.message || this._cubeLoadingMessage(),
            pct,
          ),
          pct,
        );

        if (data.done && data.result) {
          return data.result;
        }

        await this._sleep(400);
      }

      this._setTableMessage("Не удалось загрузить таблицу.");
      this._showError("Превышено время ожидания агрегации куба.");
      return null;
    }

    async _aggregateCubeSync({ showTableLoading = false, attempt = 0 } = {}) {
      if (showTableLoading || attempt > 0) {
        this._startCubeLoadProgress();
      }

      const maxAttempts = this.state.compactPending ? 45 : 8;

      try {
        const { response, data } = await fetchJson(this.cubeUrlValue, {
          method: "POST",
          body: this._cubePayload(),
        });

        if (!response.ok || !data || !data.success) {
          const message =
            (data && data.errors && data.errors.join("; ")) ||
            "Не удалось загрузить куб эффектов";
          if (
            !this.state.computing &&
            (message.includes("устарел") || message.includes("недоступен"))
          ) {
            this._stopCubeLoadProgress();
            this.state.cacheKey = null;
            this._computeEffects();
            return;
          }
          if (this.state.compactPending && attempt + 1 < maxAttempts) {
            await this._waitForCompactReady();
            return this._aggregateCubeSync({
              showTableLoading,
              attempt: attempt + 1,
            });
          }
          if (this._isCubePendingMessage(message) && attempt + 1 < maxAttempts) {
            await this._sleep(400);
            return this._aggregateCubeSync({
              showTableLoading,
              attempt: attempt + 1,
            });
          }
          this._stopCubeLoadProgress();
          this._setTableMessage("Нет данных.");
          this._showError(message);
          return;
        }

        this._stopCubeLoadProgress();
        this.state.compactPending = false;
        this.state.groupByLabel = data.group_by_label || this.state.groupByLabel;
        this.state.groupByInnerLabel = data.group_by_inner_label;
        this._renderCubeTable(data);
      } catch (error) {
        this._stopCubeLoadProgress();
        console.error("[effects-cube] aggregate failed", error);
        this._setTableMessage("Не удалось загрузить таблицу.");
        this._showError("Не удалось загрузить куб эффектов.");
      }
    }

    _cubePayload() {
      return {
        scenario_id: this.state.selectedScenarioId,
        cache_key: this.state.cacheKey,
        group_by: this.groupBySelectTarget?.value || "cargo_group",
        group_by_inner: this.groupByInnerSelectTarget?.value || "none",
        cargo_groups: this._selectedMultiValues(this.state.cargoTomSelect),
        holdings: this._selectedMultiValues(this.state.holdingTomSelect),
      };
    }

    _cubePayloadKey() {
      return JSON.stringify(this._cubePayload());
    }

    _rememberCubeResult(jobId, tableData) {
      this.state.lastCubeJobId = jobId;
      this.state.lastCubePayloadKey = this._cubePayloadKey();
      this.state.lastCubeResult = tableData;
    }

    _cubeResultMatchesCurrentFilters() {
      return (
        Boolean(this.state.lastCubeJobId) &&
        this.state.lastCubePayloadKey === this._cubePayloadKey()
      );
    }

    async _ensureCubeJobIdForExport() {
      if (this._cubeResultMatchesCurrentFilters()) {
        return this.state.lastCubeJobId;
      }

      if (!this.cubeStartUrlValue || !this.cubeStatusUrlValue) {
        return null;
      }

      const { response, data } = await fetchJson(this.cubeStartUrlValue, {
        method: "POST",
        body: this._cubePayload(),
      });
      if (!response.ok || !data || !data.success) {
        const message =
          (data && data.errors && data.errors.join("; ")) ||
          "Не удалось подготовить данные для экспорта";
        this._showError(message);
        return null;
      }

      const tableData = await this._pollCubeJobUntilDone(data.job_id);
      if (!tableData) {
        return null;
      }
      this._rememberCubeResult(data.job_id, tableData);
      return data.job_id;
    }

    async _downloadCubeExport(body) {
      const { response, blob } = await fetchBlob(this.exportUrlValue, {
        method: "POST",
        body,
      });

      if (!response.ok) {
        const contentType = response.headers.get("Content-Type") || "";
        if (contentType.includes("application/json")) {
          const text = await blob.text();
          try {
            const payload = JSON.parse(text);
            const message =
              (payload.errors && payload.errors.join("; ")) ||
              "Не удалось экспортировать таблицу.";
            this._showError(message);
            return;
          } catch (_error) {
            // fall through
          }
        }
        this._showError("Не удалось экспортировать таблицу.");
        return;
      }

      const disposition = response.headers.get("Content-Disposition") || "";
      const match = disposition.match(/filename="([^"]+)"/);
      const filename = match ? match[1] : "kub_effektov.xlsx";

      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }

    _renderCubeTable(data) {
      if (!this.hasTableWrapTarget) return;

      this.tableWrapTarget.classList.remove("effects-cube-table-wrap--loading");

      const years = data.years || [];
      const rows = (data.table && data.table.rows) || [];
      const totalLabel = data.total_column_label || "Итого";
      const showInner =
        Boolean(data.group_by_inner_label) &&
        this.groupBySelectTarget?.value !== "tariff_decision";

      if (!rows.length) {
        this._setTableMessage("Нет данных для таблицы.");
        return;
      }

      const yearHeaders = years
        .map((year) => `<th class="text-end">${escapeHtml(String(year))}</th>`)
        .join("");

      const body = rows
        .map((row) => {
          const yearCells = years
            .map((year) => {
              const value = (row.years && row.years[String(year)]) || "0.000";
              return `<td class="text-end">${escapeHtml(value)}</td>`;
            })
            .join("");

          const innerCell = showInner
            ? `<td class="group-label-cell">${escapeHtml(row.group_inner_label || "")}</td>`
            : "";

          return `
            <tr>
              <td class="group-label-cell">${escapeHtml(row.group_label || "")}</td>
              ${innerCell}
              <td class="effect-label-cell">${escapeHtml(row.effect_label || "")}</td>
              ${yearCells}
              <td class="text-end fw-bold">${escapeHtml(row.total || "0.000")}</td>
            </tr>
          `;
        })
        .join("");

      const innerHeader = showInner
        ? `<th>${escapeHtml(data.group_by_inner_label)}</th>`
        : "";

      this.tableWrapTarget.innerHTML = `
        <div class="table-responsive">
          <table class="table table-sm table-vcenter effects-cube-table">
            <thead>
              <tr>
                <th>${escapeHtml(data.group_by_label || "Группа")}</th>
                ${innerHeader}
                <th>Тарифное решение</th>
                ${yearHeaders}
                <th class="text-end">${escapeHtml(totalLabel)}</th>
              </tr>
            </thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;
    }

    _setTableLoading(isLoading, message = "Загрузка…", progressPct = null) {
      if (!this.hasTableWrapTarget) return;
      this.tableWrapTarget.classList.toggle(
        "effects-cube-table-wrap--loading",
        isLoading,
      );
      if (isLoading) {
        const hasProgress =
          typeof progressPct === "number" && Number.isFinite(progressPct);
        const pct = hasProgress
          ? Math.max(0, Math.min(100, Math.round(progressPct)))
          : null;
        const progressBar = hasProgress
          ? `
          <div class="progress mt-3 mx-auto" style="max-width: 20rem; height: 0.5rem;">
            <div
              class="progress-bar progress-bar-striped progress-bar-animated"
              role="progressbar"
              style="width: ${pct}%"
              aria-valuenow="${pct}"
              aria-valuemin="0"
              aria-valuemax="100"
            ></div>
          </div>`
          : "";
        this.tableWrapTarget.innerHTML = `
          <div class="text-muted py-4 text-center effects-cube-table-loading">
            <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
            <div class="mt-2">${escapeHtml(message)}</div>
            ${progressBar}
          </div>
        `;
      }
    }

    _setTableMessage(message) {
      if (!this.hasTableWrapTarget) return;
      this.tableWrapTarget.classList.remove("effects-cube-table-wrap--loading");
      this.tableWrapTarget.innerHTML = `<div class="text-muted py-4 text-center">${escapeHtml(message)}</div>`;
    }

    _syncFilterOptions(filterOptions) {
      this.state.suppressFilterEvents = true;
      this._populateMultiSelect(
        this.cargoFilterSelectTarget,
        filterOptions.cargo_groups || [],
        "cargoTomSelect",
      );
      this._populateMultiSelect(
        this.holdingFilterSelectTarget,
        filterOptions.holdings || [],
        "holdingTomSelect",
      );
      this.state.suppressFilterEvents = false;
    }

    _populateMultiSelect(selectEl, options, stateKey) {
      if (!selectEl) return;

      const previous = this._selectedMultiValues(this.state[stateKey]);
      selectEl.innerHTML = "";
      for (const value of options) {
        const opt = document.createElement("option");
        opt.value = value;
        opt.textContent = value;
        selectEl.appendChild(opt);
      }

      this._destroyTomSelect(stateKey);
      if (typeof TomSelect !== "undefined") {
        this.state[stateKey] = new TomSelect(selectEl, {
          plugins: ["remove_button"],
          maxItems: null,
          placeholder: "Все",
          onChange: () => this.onFilterChange(),
        });
        if (previous.length) {
          this.state[stateKey].setValue(
            previous.filter((item) => options.includes(item)),
            true,
          );
        }
      }
    }

    _destroyTomSelects() {
      this._destroyTomSelect("cargoTomSelect");
      this._destroyTomSelect("holdingTomSelect");
    }

    _destroyTomSelect(stateKey) {
      const instance = this.state[stateKey];
      if (instance && typeof instance.destroy === "function") {
        instance.destroy();
      }
      this.state[stateKey] = null;
    }

    _selectedMultiValues(tomSelectInstance) {
      if (tomSelectInstance && typeof tomSelectInstance.getValue === "function") {
        const value = tomSelectInstance.getValue();
        if (Array.isArray(value)) return value;
        return value ? [value] : [];
      }
      return [];
    }

    async _exportCube() {
      if (!this.exportUrlValue) {
        return;
      }
      if (!this.state.cacheKey) {
        this._showError("Сначала дождитесь расчёта таблицы.");
        return;
      }

      this.state.exporting = true;
      this._showRebuildStatus("Формирование отчёта…", "info");

      try {
        if (this.cubeStartUrlValue && this.cubeStatusUrlValue) {
          const jobId = await this._ensureCubeJobIdForExport();
          if (!jobId) {
            return;
          }
          await this._downloadCubeExport({ job_id: jobId });
          return;
        }

        await this._downloadCubeExport(this._cubePayload());
      } catch (error) {
        console.error("[effects-cube] export failed", error);
        this._showError("Не удалось экспортировать таблицу.");
      } finally {
        this.state.exporting = false;
        this._hideRebuildStatus();
      }
    }

    _toastOptions(extra = {}) {
      return {
        container: this.hasToastContainerTarget
          ? this.toastContainerTarget
          : undefined,
        ...extra,
      };
    }

    _renderWarning(routesWithoutCharge, routesWithoutVolume, _meta = {}) {
      const chargeCount = Number(routesWithoutCharge) || 0;
      const volumeCount = Number(routesWithoutVolume) || 0;

      const warnings = [];
      if (chargeCount > 0) {
        warnings.push(
          `${chargeCount} маршрут(ов) без провозной платы не учтены в расчёте.`,
        );
      }
      if (volumeCount > 0) {
        warnings.push(
          `${volumeCount} маршрут(ов) без объёма перевозок не учтены.`,
        );
      }
      if (warnings.length) {
        showToast(
          warnings,
          this._toastOptions({
            variant: "warning",
            delay: 9000,
          }),
        );
      }
    }

    _showError(message) {
      if (!message) return;
      showToast(
        message,
        this._toastOptions({
          variant: "error",
          delay: 8000,
        }),
      );
    }

    _persistActiveScenario(scenarioId) {
      if (!scenarioId) return;

      const scenario = this.state.scenarioById.get(scenarioId);
      const activeRaw = (this.activeScenarioIdValue || "").trim();
      const activeId = activeRaw ? Number(activeRaw) : null;
      if (activeId === scenarioId) return;

      void persistActiveScenario(scenarioId, {
        routeSetId: scenario?.route_set_id,
        onError: (errors) => {
          this._showError(
            (errors && errors.join("; ")) ||
              "Не удалось сохранить активный сценарий",
          );
        },
      }).then((ok) => {
        if (ok) {
          this.activeScenarioIdValue = String(scenarioId);
        }
      });
    }

    _clearToasts() {
      clearToasts(
        this.hasToastContainerTarget ? this.toastContainerTarget : undefined,
      );
    }
  }

  application.register("effects-cube", EffectsCubeController);
})();
