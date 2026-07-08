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
    console.error("Stimulus is not available for decision-effects.");
    return;
  }

  class DecisionEffectsController extends Stimulus.Controller {
    static targets = [
      "scenarioSelect",
      "scenarioEditButton",
      "kpiCards",
      "groupBySelect",
      "groupByInnerSelect",
      "cargoFilterSelect",
      "holdingFilterSelect",
      "yearSelect",
      "tableWrap",
      "chartWrap",
      "chartCanvas",
      "toastContainer",
      "revenuesGroupBySelect",
      "revenuesGroupByInnerSelect",
      "revenuesTableWrap",
      "volumesGroupBySelect",
      "volumesGroupByInnerSelect",
      "volumesTableWrap",
      "revenuesFalloutToggle",
      "volumesFalloutToggle",
      "revenuesFalloutControl",
      "revenuesFalloutDisabledHint",
      "volumesFalloutControl",
      "volumesFalloutDisabledHint",
      "rebuildStatus",
    ];

    static values = {
      scenariosUrl: String,
      computeUrl: String,
      computePandasUrl: String,
      aggregateUrl: String,
      revisionUrl: String,
      cacheReadinessUrl: String,
      warmStatusUrl: String,
      compactStatusUrl: String,
      revenuesUrl: String,
      volumesUrl: String,
      revenuesExportUrl: String,
      volumesExportUrl: String,
      activeScenarioId: String,
      scenarioEditUrl: String,
      debounceMs: { type: Number, default: 350 },
    };

    connect() {
      this.state = {
        scenarioById: new Map(),
        selectedScenarioId: null,
        cacheKey: null,
        effectYears: [],
        chart: null,
        cargoTomSelect: null,
        holdingTomSelect: null,
        aggregateTimer: null,
        revenuesTimer: null,
        volumesTimer: null,
        scenarioYears: [],
        suppressFilterEvents: false,
        computing: false,
        compactPending: false,
        effectsCompactPending: false,
        awaitingCompact: false,
        earlyGroupReady: false,
        lastDataVersion: null,
        revisionTimer: null,
        scenarioEditModal: null,
        scenarioEditModalEl: null,
        scenarioEditFrame: null,
        boundScenarioEditModalHiddenHandler: null,
        showFalloutAdjustedRevenues: false,
        showFalloutAdjustedVolumes: false,
      };

      this.state.scenarioEditModalEl = document.getElementById(
        "decisionEffectsScenarioEditModal",
      );
      this.state.scenarioEditFrame = document.getElementById(
        "decisionEffectsScenarioEditFrame",
      );
      if (this.state.scenarioEditModalEl && typeof bootstrap !== "undefined") {
        this.state.scenarioEditModal =
          bootstrap.Modal.getInstance(this.state.scenarioEditModalEl) ||
          bootstrap.Modal.getOrCreateInstance(this.state.scenarioEditModalEl);
        this.state.boundScenarioEditModalHiddenHandler =
          this._onScenarioEditModalHidden.bind(this);
        this.state.scenarioEditModalEl.addEventListener(
          "hidden.bs.modal",
          this.state.boundScenarioEditModalHiddenHandler,
        );
      }

      this._onVisibilityChange = this._onVisibilityChange.bind(this);
      this._onScenarioRecalculated = this._onScenarioRecalculated.bind(this);
      this._onScenarioEditMessage = this._onScenarioEditMessage.bind(this);
      document.addEventListener("visibilitychange", this._onVisibilityChange);
      document.addEventListener("scenario-recalculated", this._onScenarioRecalculated);
      window.addEventListener("message", this._onScenarioEditMessage);
      this.state.revisionTimer = setInterval(
        () => this._checkRevision(),
        30000,
      );

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
      document.removeEventListener("visibilitychange", this._onVisibilityChange);
      document.removeEventListener("scenario-recalculated", this._onScenarioRecalculated);
      window.removeEventListener("message", this._onScenarioEditMessage);
      if (
        this.state?.scenarioEditModalEl &&
        this.state?.boundScenarioEditModalHiddenHandler
      ) {
        this.state.scenarioEditModalEl.removeEventListener(
          "hidden.bs.modal",
          this.state.boundScenarioEditModalHiddenHandler,
        );
      }
      if (this.state?.revisionTimer) {
        clearInterval(this.state.revisionTimer);
        this.state.revisionTimer = null;
      }
      this._destroyChart();
      this._destroyTomSelects();
    }

    onScenarioChange() {
      const raw = this.hasScenarioSelectTarget
        ? this.scenarioSelectTarget.value
        : "";
      const scenarioId = raw ? Number(raw) : null;
      this.state.selectedScenarioId = scenarioId;
      this.state.cacheKey = null;
      this._resetFalloutToggles();
      this._updateFalloutControlsVisibility();
      this._updateScenarioEditButtonState();
      this._persistActiveScenario(scenarioId);
      this._computeEffects();
    }

    openScenarioEditModal() {
      const scenarioId = this.state.selectedScenarioId;
      if (!scenarioId || !this.state.scenarioEditFrame) return;

      const url = this._buildScenarioEditUrl(scenarioId);
      if (!url) return;

      this.state.scenarioEditFrame.src = url;
      if (this.state.scenarioEditModal) {
        this.state.scenarioEditModal.show();
      }
    }

    async _onScenarioEditModalHidden() {
      if (this.state.scenarioEditFrame) {
        this.state.scenarioEditFrame.src = "about:blank";
      }

      const prevId = this.state.selectedScenarioId;
      try {
        await this._loadScenarios();
        if (prevId != null && this.state.scenarioById.has(prevId)) {
          if (this.hasScenarioSelectTarget) {
            this.scenarioSelectTarget.value = String(prevId);
          }
          this.state.selectedScenarioId = prevId;
          this._updateScenarioEditButtonState();
          this._updateFalloutControlsVisibility();
        }
      } catch (e) {
        console.error("[decision-effects] scenario list refresh failed", e);
      }
    }

    _buildScenarioEditUrl(scenarioId) {
      const template = (this.scenarioEditUrlValue || "").trim();
      if (!template || scenarioId == null) return null;
      return `${template.replace("/0/", `/${scenarioId}/`)}?embed=1`;
    }

    _updateScenarioEditButtonState() {
      if (!this.hasScenarioEditButtonTarget) return;
      this.scenarioEditButtonTarget.disabled =
        this.state.selectedScenarioId == null;
    }

    onFilterChange() {
      if (this.state.suppressFilterEvents) return;
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

      clearTimeout(this.state.aggregateTimer);
      this.state.aggregateTimer = setTimeout(() => {
        this._aggregateEffects();
      }, this.debounceMsValue || 350);
    }

    onRevenuesFilterChange() {
      this._fixInnerGroupConflict(
        this.revenuesGroupBySelectTarget,
        this.revenuesGroupByInnerSelectTarget,
      );
      this._setRevenuesTableLoading(true);
      clearTimeout(this.state.revenuesTimer);
      this.state.revenuesTimer = setTimeout(() => {
        this._aggregateRevenues();
      }, this.debounceMsValue || 350);
    }

    onVolumesFilterChange() {
      this._fixInnerGroupConflict(
        this.volumesGroupBySelectTarget,
        this.volumesGroupByInnerSelectTarget,
      );
      this._setVolumesTableLoading(true);
      clearTimeout(this.state.volumesTimer);
      this.state.volumesTimer = setTimeout(() => {
        this._aggregateVolumes();
      }, this.debounceMsValue || 350);
    }

    onRevenuesExport() {
      this._exportAbsolute("revenues");
    }

    onVolumesExport() {
      this._exportAbsolute("volumes");
    }

    async onRevenuesFalloutToggle() {
      this.state.showFalloutAdjustedRevenues = Boolean(
        this.hasRevenuesFalloutToggleTarget &&
          this.revenuesFalloutToggleTarget.checked,
      );
      await this._handleAbsoluteFalloutToggle("revenues");
    }

    async onVolumesFalloutToggle() {
      this.state.showFalloutAdjustedVolumes = Boolean(
        this.hasVolumesFalloutToggleTarget &&
          this.volumesFalloutToggleTarget.checked,
      );
      await this._handleAbsoluteFalloutToggle("volumes");
    }

    async _handleAbsoluteFalloutToggle(kind) {
      if (!this.state.cacheKey || !this.state.selectedScenarioId) {
        return;
      }

      const includeFallout = this._includeFalloutForKind(kind);
      if (includeFallout) {
        if (kind === "revenues") {
          this._setRevenuesTableLoading(true, "Расчёт выпадения…");
        } else {
          this._setVolumesTableLoading(true, "Расчёт выпадения…");
        }
        await this._ensureCompactReady();
      }

      if (kind === "revenues") {
        await this._aggregateRevenues();
      } else {
        await this._aggregateVolumes();
      }
    }

    _resetFalloutToggles() {
      this.state.showFalloutAdjustedRevenues = false;
      this.state.showFalloutAdjustedVolumes = false;
      if (this.hasRevenuesFalloutToggleTarget) {
        this.revenuesFalloutToggleTarget.checked = false;
      }
      if (this.hasVolumesFalloutToggleTarget) {
        this.volumesFalloutToggleTarget.checked = false;
      }
    }

    _isElasticityEnabled() {
      const scenarioId = this.state.selectedScenarioId;
      if (!scenarioId) {
        return false;
      }
      const scenario = this.state.scenarioById.get(scenarioId);
      return Boolean(scenario && scenario.consider_demand_elasticity);
    }

    _updateFalloutControlsVisibility() {
      const scenarioSelected = Boolean(this.state.selectedScenarioId);
      const elasticityEnabled = this._isElasticityEnabled();
      const showControl = scenarioSelected && elasticityEnabled;
      const showHint = scenarioSelected && !elasticityEnabled;

      this._toggleFalloutBlock("revenues", showControl, showHint);
      this._toggleFalloutBlock("volumes", showControl, showHint);
    }

    _toggleFalloutBlock(kind, showControl, showHint) {
      const controlTarget = `${kind}FalloutControlTarget`;
      const hintTarget = `${kind}FalloutDisabledHintTarget`;
      const hasControl = `has${kind.charAt(0).toUpperCase()}${kind.slice(1)}FalloutControlTarget`;
      const hasHint = `has${kind.charAt(0).toUpperCase()}${kind.slice(1)}FalloutDisabledHintTarget`;

      if (this[hasControl]) {
        this[controlTarget].classList.toggle("d-none", !showControl);
      }
      if (this[hasHint]) {
        this[hintTarget].classList.toggle("d-none", !showHint);
      }
    }

    _includeFalloutForKind(kind) {
      if (!this._isElasticityEnabled()) {
        return false;
      }
      return kind === "revenues"
        ? Boolean(this.state.showFalloutAdjustedRevenues)
        : Boolean(this.state.showFalloutAdjustedVolumes);
    }

    _fixInnerGroupConflict(outerSelect, innerSelect) {
      if (
        outerSelect &&
        innerSelect &&
        innerSelect.value !== "none" &&
        innerSelect.value === outerSelect.value
      ) {
        innerSelect.value = "none";
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
        this.state.selectedScenarioId = null;
        this._updateScenarioEditButtonState();
        this._updateFalloutControlsVisibility();
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
        this._updateScenarioEditButtonState();
        this._updateFalloutControlsVisibility();
        this._computeEffects();
      }
    }

    _resolveComputeUrl() {
      return this.computePandasUrlValue || this.computeUrlValue;
    }

    async _computeEffects() {
      const computeUrl = this._resolveComputeUrl();
      if (!computeUrl || !this.state.selectedScenarioId) return;

      this._clearToasts();
      const readiness = await this._waitForCacheReadiness(
        this.state.selectedScenarioId,
      );
      if (
        readiness &&
        (readiness.mart_phase === "error" || readiness.scenario_phase === "error")
      ) {
        return;
      }
      this._setKpiLoading(true);
      this._setChartLoading(true, "Расчёт данных…");
      this._setRevenuesTableLoading(true, "Расчёт данных…");
      this._setVolumesTableLoading(true, "Расчёт данных…");
      this.state.computing = true;

      try {
        const { response, data } = await fetchJson(computeUrl, {
          method: "POST",
          body: {
            scenario_id: this.state.selectedScenarioId,
            include_rule_breakdown: false,
          },
        });

        if (!response.ok || !data || !data.success) {
          if (response.status === 409 && data && data.code === "mart_rebuilding") {
            this._hideRebuildStatus();
            this._showRouteMartRebuildModal(cacheReadinessMessage(data));
            const waited = await this._waitForCacheReadiness(
              this.state.selectedScenarioId,
            );
            if (
              !waited ||
              waited.mart_phase === "error" ||
              waited.scenario_phase === "error"
            ) {
              return;
            }
            return this._computeEffects();
          }
          this.state.cacheKey = null;
          this._renderKpiCards([]);
          this._setChartLoading(false);
          this._setRevenuesTableLoading(false);
          this._setVolumesTableLoading(false);
          if (this.hasRevenuesTableWrapTarget) {
            this.revenuesTableWrapTarget.innerHTML =
              '<div class="text-muted py-4 text-center">—</div>';
          }
          if (this.hasVolumesTableWrapTarget) {
            this.volumesTableWrapTarget.innerHTML =
              '<div class="text-muted py-4 text-center">—</div>';
          }
          this._showError(
            (data && data.errors && data.errors.join("; ")) ||
              "Ошибка расчёта эффектов",
          );
          return;
        }

        this.state.cacheKey = data.cache_key || null;
        this.state.compactPending = data.compact_ready === false;
        this.state.effectsCompactPending = data.compact_ready === false;
        this.state.awaitingCompact = data.compact_ready === false;
        this.state.earlyGroupReady = Boolean(
          data.early_group_ready ?? data.compact_ready,
        );
        this.state.lastDataVersion = data.data_version || null;
        if (this.state.compactPending) {
          this._setCompactPendingIndicator(true);
        }
        this.state.scenarioYears = data.years || [];
        this._renderWarning(
          data.routes_without_charge,
          data.routes_without_volume,
          {
            engine: data.engine,
            elapsed_ms: data.elapsed_ms,
            timings: data.timings,
            scenario_compute_cache_hit: data.scenario_compute_cache_hit,
            compact_ready: data.compact_ready,
          },
        );
        this._syncYearOptions(data.years || []);
        this._syncFilterOptions(data.filter_options || {});
        this._renderKpiCards(data.cards || []);

        const useEarlyAbsolute = this._canUseEarlyAbsolute();
        await Promise.all([
          this._aggregateEffects({ showTableLoading: true }),
          ...(useEarlyAbsolute
            ? [this._aggregateRevenues(), this._aggregateVolumes()]
            : []),
        ]);

        if (this.state.awaitingCompact) {
          if (useEarlyAbsolute) {
            await this._refreshAbsoluteWhenCompactReady();
          } else {
            await this._ensureCompactReady();
            await Promise.all([
              this._aggregateEffects({ showTableLoading: true }),
              this._aggregateRevenues(),
              this._aggregateVolumes(),
            ]);
          }
        } else if (!useEarlyAbsolute) {
          await Promise.all([
            this._aggregateRevenues(),
            this._aggregateVolumes(),
          ]);
        }

        this.state.awaitingCompact = false;
      } catch (error) {
        console.error("[decision-effects] compute failed", error);
        this.state.cacheKey = null;
        this._renderKpiCards([]);
        this._setChartLoading(false);
        this._setRevenuesTableLoading(false);
        this._setVolumesTableLoading(false);
        if (this.hasRevenuesTableWrapTarget) {
          this.revenuesTableWrapTarget.innerHTML =
            '<div class="text-muted py-4 text-center">—</div>';
        }
        if (this.hasVolumesTableWrapTarget) {
          this.volumesTableWrapTarget.innerHTML =
            '<div class="text-muted py-4 text-center">—</div>';
        }
        this._showError(
          "Не удалось выполнить расчёт. Попробуйте обновить страницу.",
        );
      } finally {
        this.state.computing = false;
        this._setKpiLoading(false);
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

    async _aggregateEffects({ showTableLoading = false, attempt = 0 } = {}) {
      if (
        !this.aggregateUrlValue ||
        !this.state.selectedScenarioId ||
        !this.state.cacheKey
      ) {
        return;
      }

      const year =
        this._selectedYear() ||
        this.state.effectYears[0] ||
        this._defaultEffectYear();
      if (!year) {
        this._showError("Не удалось определить год для расчёта");
        return;
      }

      if (showTableLoading && attempt === 0) {
        this._setTableLoading(true);
        this._setChartLoading(true, "Обновление диаграммы…");
      }

      const maxAttempts = this.state.effectsCompactPending ? 45 : 5;

      try {
        const payload = {
          scenario_id: this.state.selectedScenarioId,
          cache_key: this.state.cacheKey,
          year,
          group_by: this.hasGroupBySelectTarget
            ? this.groupBySelectTarget.value
            : "cargo_group",
          group_by_inner: this.hasGroupByInnerSelectTarget
            ? this.groupByInnerSelectTarget.value
            : "none",
          cargo_groups: this._selectedMultiValues(this.state.cargoTomSelect),
          holdings: this._selectedMultiValues(this.state.holdingTomSelect),
        };

        const { response, data } = await fetchJson(this.aggregateUrlValue, {
          method: "POST",
          body: payload,
        });

        if (!response.ok || !data || !data.success) {
          const message =
            (data && data.errors && data.errors.join("; ")) ||
            "Ошибка агрегации эффектов";
          if (
            message.includes("устарел") ||
            message.includes("недоступен")
          ) {
            this.state.cacheKey = null;
            await this._computeEffects();
            return;
          }
          if (
            (this.state.effectsCompactPending ||
              this._isAggregatePendingMessage(message)) &&
            attempt + 1 < maxAttempts
          ) {
            await this._waitForCompactReady();
            return this._aggregateEffects({
              showTableLoading,
              attempt: attempt + 1,
            });
          }
          this._showError(message);
          if (showTableLoading) {
            this._setTableLoading(false);
            this._setChartLoading(false);
          }
          return;
        }

        this.state.effectsCompactPending = false;
        if (!this.state.awaitingCompact) {
          this.state.compactPending = false;
          this._setCompactPendingIndicator(false);
        }
        this._renderTable(
          data.table && data.table.rows ? data.table.rows : [],
          Boolean(data.table && data.table.show_fallout),
        );
        this._renderChart(data.chart || null);
        if (showTableLoading) {
          this._setTableLoading(false);
          this._setChartLoading(false);
        }
      } catch (error) {
        console.error("[decision-effects] aggregate failed", error);
        if (attempt + 1 < maxAttempts) {
          await this._sleep(2000);
          return this._aggregateEffects({
            showTableLoading,
            attempt: attempt + 1,
          });
        }
        this._showError("Не удалось обновить таблицу и график.");
        if (showTableLoading) {
          this._setTableLoading(false);
          this._setChartLoading(false);
        }
      }
    }

    _isAggregatePendingMessage(message) {
      return (
        typeof message === "string" &&
        (message.includes("ещё выполняется") ||
          message.includes("еще выполняется"))
      );
    }

    _sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async _waitForCompactReady() {
      if (!this.compactStatusUrlValue || !this.state.cacheKey) {
        await this._sleep(2000);
        return;
      }

      try {
        const { data } = await fetchJson(this.compactStatusUrlValue, {
          method: "POST",
          body: { cache_key: this.state.cacheKey },
        });
        if (data && data.success) {
          if (!data.compact_ready) {
            this.state.compactPending = true;
          }
          if (data.compact_ready) {
            this.state.awaitingCompact = false;
          }
          if (data.early_group_ready) {
            this.state.earlyGroupReady = true;
          }
          if (data.data_version) {
            this.state.lastDataVersion = data.data_version;
          }
        }
      } catch (error) {
        console.error("[decision-effects] compact-status failed", error);
      }
      await this._sleep(2000);
    }

    async _ensureCompactReady() {
      if (!this.state.awaitingCompact && !this.state.compactPending) {
        return true;
      }

      const maxAttempts = 45;
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        if (!this.state.cacheKey) {
          return false;
        }

        if (this.compactStatusUrlValue) {
          try {
            const { data } = await fetchJson(this.compactStatusUrlValue, {
              method: "POST",
              body: { cache_key: this.state.cacheKey },
            });
        if (data?.success && data.compact_ready) {
          this.state.compactPending = false;
          this.state.awaitingCompact = false;
          this.state.earlyGroupReady = true;
          this._setCompactPendingIndicator(false);
          return true;
        }
        if (data?.success && data.early_group_ready) {
          this.state.earlyGroupReady = true;
        }
          } catch (error) {
            console.error("[decision-effects] compact-status failed", error);
          }
        }

        this._setRevenuesTableLoading(true, "Обновление детализации…");
        this._setVolumesTableLoading(true, "Обновление детализации…");
        await this._sleep(2000);
      }

      return false;
    }

    _onVisibilityChange() {
      if (document.visibilityState === "visible") {
        this._checkRevision();
      }
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
      if (!event.data || !event.data.type) return;
      if (event.data.type === "close-scenario-edit-modal") {
        this._closeScenarioEditModal();
        return;
      }
      if (event.data.type === "scenario-recalculated") {
        this._onScenarioRecalculated({ detail: { scenarioId: event.data.scenarioId } });
      }
    }

    _closeScenarioEditModal() {
      if (this.state.scenarioEditModal) {
        this.state.scenarioEditModal.hide();
      }
    }

    async _handleScenarioRecalculated() {
      if (this.state.computing) {
        return;
      }
      this._setKpiLoading(true);
      await this._waitForWarmKpi(this.state.selectedScenarioId);
      await this._checkRevision(true);
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
        if (!data || !data.success) {
          await this._sleep(300);
          return this._waitForWarmKpi(scenarioId, startedAt);
        }
        if (!data.phase) {
          return;
        }
        if (data.phase === "error") {
          console.error("[decision-effects] scenario warm failed", data.error);
          return;
        }
        if (data.kpi_ready || data.phase === "done" || data.compact_ready) {
          return;
        }
        await this._sleep(300);
        return this._waitForWarmKpi(scenarioId, startedAt);
      } catch (error) {
        console.error("[decision-effects] warm status poll failed", error);
        await this._sleep(500);
        return this._waitForWarmKpi(scenarioId, startedAt);
      }
    }

    _sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async _checkRevision(forceRecompute = false) {
      if (!this.revisionUrlValue || !this.state.selectedScenarioId) {
        return;
      }
      if (this.state.computing) {
        return;
      }

      try {
        const url = `${this.revisionUrlValue}?scenario_id=${encodeURIComponent(
          String(this.state.selectedScenarioId),
        )}`;
        const { data } = await fetchJson(url);
        if (!data || !data.success || !data.data_version) {
          return;
        }
        if (
          forceRecompute ||
          (this.state.lastDataVersion &&
            data.data_version !== this.state.lastDataVersion)
        ) {
          await this._computeEffects();
        }
      } catch (error) {
        console.error("[decision-effects] revision check failed", error);
      }
    }

    _setCompactPendingIndicator(isPending) {
      if (!this.hasKpiCardsTarget) return;
      const existing = this.kpiCardsTarget.querySelector("[data-compact-pending]");
      if (!isPending) {
        if (existing) {
          existing.remove();
        }
        return;
      }
      if (existing) {
        return;
      }
      const wrapper = document.createElement("div");
      wrapper.dataset.compactPending = "1";
      wrapper.innerHTML = `
        <div class="alert alert-info py-2 px-3 mb-2 w-100" role="status">
          <span class="spinner-border spinner-border-sm text-primary me-2" role="status"></span>
          Обновление детализации…
        </div>
      `;
      this.kpiCardsTarget.prepend(wrapper);
      if (this.hasTableWrapTarget) {
        this.tableWrapTarget.innerHTML = this._tableLoadingHtml(
          "Обновление детализации…",
        );
      }
      this._setChartLoading(true, "Обновление детализации…");
      this._setRevenuesTableLoading(true, "Обновление детализации…");
      this._setVolumesTableLoading(true, "Обновление детализации…");
    }

    _setKpiLoading(isLoading) {
      if (!this.hasKpiCardsTarget) return;
      if (!isLoading) return;
      this.kpiCardsTarget.innerHTML = `
        <div class="text-muted py-4 w-100 text-center">
          <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
          <div class="mt-2">Расчёт эффектов…</div>
        </div>
      `;
    }

    _setTableLoading(isLoading) {
      if (!this.hasTableWrapTarget) return;
      if (!isLoading) return;
      this.tableWrapTarget.innerHTML = this._tableLoadingHtml(
        "Обновление таблицы…",
      );
    }

    _setChartLoading(isLoading, message = "Обновление диаграммы…") {
      if (!this.hasChartWrapTarget) return;

      const wrap = this.chartWrapTarget;
      let overlay = wrap.querySelector("[data-chart-loading]");

      if (!isLoading) {
        wrap.classList.remove("decision-effects-chart-wrap--loading");
        if (overlay) {
          overlay.remove();
        }
        return;
      }

      wrap.classList.add("decision-effects-chart-wrap--loading");
      if (overlay) {
        const messageEl = overlay.querySelector("[data-chart-loading-message]");
        if (messageEl) {
          messageEl.textContent = message;
        }
        return;
      }

      overlay = document.createElement("div");
      overlay.dataset.chartLoading = "1";
      overlay.className = "decision-effects-chart-loading";
      overlay.innerHTML = `
        <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
        <div class="mt-2 text-muted" data-chart-loading-message>${escapeHtml(message)}</div>
      `;
      wrap.appendChild(overlay);
    }

    _tableLoadingHtml(message) {
      return `
        <div class="text-muted py-4 text-center decision-effects-table-loading">
          <div class="spinner-border spinner-border-sm text-primary" role="status"></div>
          <div class="mt-2">${escapeHtml(message)}</div>
        </div>
      `;
    }

    _setRevenuesTableLoading(isLoading, message = "Обновление таблицы…") {
      if (!this.hasRevenuesTableWrapTarget) return;
      this._setAbsoluteTableLoading(
        this.revenuesTableWrapTarget,
        isLoading,
        message,
      );
    }

    _setVolumesTableLoading(isLoading, message = "Обновление таблицы…") {
      if (!this.hasVolumesTableWrapTarget) return;
      this._setAbsoluteTableLoading(
        this.volumesTableWrapTarget,
        isLoading,
        message,
      );
    }

    _setAbsoluteTableLoading(wrapEl, isLoading, message) {
      if (!wrapEl) return;
      if (!isLoading) {
        wrapEl.classList.remove(
          "decision-effects-absolute-table-wrap--loading",
        );
        return;
      }
      wrapEl.classList.add("decision-effects-absolute-table-wrap--loading");
      wrapEl.innerHTML = this._tableLoadingHtml(message);
    }

    _toastOptions(extra = {}) {
      return {
        container: this.hasToastContainerTarget
          ? this.toastContainerTarget
          : undefined,
        ...extra,
      };
    }

    _clearToasts() {
      clearToasts(
        this.hasToastContainerTarget ? this.toastContainerTarget : undefined,
      );
    }

    _renderWarning(_skippedCharge, _skippedVolume, _meta = {}) {}

    _showError(message) {
      if (!message) {
        return;
      }
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

    _syncYearOptions(years) {
      if (!this.hasYearSelectTarget || !Array.isArray(years) || years.length < 2) {
        return;
      }

      const effectYears = years.slice(1);
      this.state.effectYears = effectYears;

      const current = this.yearSelectTarget.value;
      this.state.suppressFilterEvents = true;
      this.yearSelectTarget.innerHTML = "";
      for (const y of effectYears) {
        const opt = document.createElement("option");
        opt.value = String(y);
        opt.textContent = String(y);
        this.yearSelectTarget.appendChild(opt);
      }

      if (current && effectYears.includes(Number(current))) {
        this.yearSelectTarget.value = current;
      } else {
        this.yearSelectTarget.value = String(effectYears[0]);
      }
      this.state.suppressFilterEvents = false;
    }

    _syncFilterOptions(filterOptions) {
      this.state.suppressFilterEvents = true;
      this._syncTomSelect(
        "cargoTomSelect",
        this.cargoFilterSelectTarget,
        filterOptions.cargo_groups || [],
      );
      this._syncTomSelect(
        "holdingTomSelect",
        this.holdingFilterSelectTarget,
        filterOptions.holdings || [],
      );
      this.state.suppressFilterEvents = false;
    }

    _syncTomSelect(stateKey, selectEl, options) {
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

    _selectedYear() {
      if (!this.hasYearSelectTarget) return null;
      const year = Number(this.yearSelectTarget.value);
      return Number.isFinite(year) ? year : null;
    }

    _defaultEffectYear() {
      const scenario = this.state.scenarioById.get(this.state.selectedScenarioId);
      if (!scenario) return null;
      const start = Number(scenario.start_year);
      if (!Number.isFinite(start)) return null;
      return start + 1;
    }

    _renderKpiCards(cards) {
      if (!this.hasKpiCardsTarget) return;

      if (!cards.length) {
        this.kpiCardsTarget.innerHTML =
          '<div class="text-muted py-4">Нет данных для карточек.</div>';
        return;
      }

      const selectedScenario = this.state.scenarioById.get(
        this.state.selectedScenarioId,
      );
      const includeBase =
        selectedScenario == null
          ? true
          : selectedScenario.include_base_tariff_decisions !== false;

      this.kpiCardsTarget.innerHTML = cards
        .map((card) => {
          const totalPct = this._formatSignedPct(card.total_pct);
          const basePct = this._formatSignedPct(card.base_pct);
          const rulesPct = this._formatSignedPct(card.rules_pct);

          const baseBlnNum = Number(String(card.base_bln).replace(",", "."));
          const rulesBlnNum = Number(String(card.rules_bln).replace(",", "."));
          const showBaseSplit =
            includeBase && Number.isFinite(baseBlnNum) && baseBlnNum !== 0;
          const showRulesSplit =
            includeBase && Number.isFinite(rulesBlnNum) && rulesBlnNum !== 0;
          const showSplit = showBaseSplit || showRulesSplit;
          return `
            <article class="decision-effects-kpi-card">
              <div class="decision-effects-kpi-card__year">${escapeHtml(String(card.year))} год</div>
              <div class="decision-effects-kpi-card__body">
                <div class="decision-effects-kpi-card__info">
                  <div class="decision-effects-kpi-card__count">
                    <span class="decision-effects-kpi-card__total-value">${escapeHtml(card.total_bln)}</span>
                    <span class="decision-effects-kpi-card__total-unit">млрд</span>
                    <span class="decision-effects-kpi-card__total-caption-pct ${escapeHtml(totalPct.className)}">${escapeHtml(totalPct.text)}</span>
                  </div>
                </div>
                ${
                  showSplit
                    ? `<div class="decision-effects-kpi-card__split">
                  ${
                    showBaseSplit
                      ? `<div class="decision-effects-kpi-card__split-item is-base">
                    <span class="decision-effects-kpi-card__split-label">Базовые решения</span>
                    <div class="decision-effects-kpi-card__count">
                      <span class="decision-effects-kpi-card__split-value">${escapeHtml(card.base_bln)}</span>
                      <span class="decision-effects-kpi-card__split-unit">млрд</span>
                    </div>
                    <span class="decision-effects-kpi-card__split-pct ${escapeHtml(basePct.className)}">${escapeHtml(basePct.text)}</span>
                  </div>`
                      : ""
                  }
                  ${
                    showRulesSplit
                      ? `<div class="decision-effects-kpi-card__split-item is-rules">
                    <span class="decision-effects-kpi-card__split-label">Отдельные решения</span>
                    <div class="decision-effects-kpi-card__count">
                      <span class="decision-effects-kpi-card__split-value">${escapeHtml(card.rules_bln)}</span>
                      <span class="decision-effects-kpi-card__split-unit">млрд</span>
                    </div>
                    <span class="decision-effects-kpi-card__split-pct ${escapeHtml(rulesPct.className)}">${escapeHtml(rulesPct.text)}</span>
                  </div>`
                      : ""
                  }
                </div>`
                    : ""
                }
              </div>
            </article>          `;
        })
        .join("");
    }

    _formatSignedMagnitude(value) {
      const raw = String(value ?? "").trim();
      if (!raw || raw === "0" || raw === "0.0") {
        return { text: raw || "0.0", className: "text-muted" };
      }
      const num = Number(raw.replace(",", "."));
      if (!Number.isFinite(num) || num === 0) {
        return { text: raw, className: "text-muted" };
      }
      const sign = num > 0 ? "+" : "-";
      return {
        text: `${sign}${raw.replace(/^[-+]/, "")}`,
        className: num > 0 ? "text-success" : "text-danger",
      };
    }

    _formatEffectsFalloutCell(row) {
      if (row.fallout_bln == null) {
        return '<td class="text-end text-muted">—</td>';
      }
      const money = this._formatSignedMagnitude(row.fallout_bln);
      const volume = this._formatSignedMagnitude(row.fallout_volume_mln_t || "0.0");
      return `<td class="text-end">
        <span class="${escapeHtml(money.className)}">${escapeHtml(money.text)} млрд</span><br />
        <span class="cell-pct ${escapeHtml(volume.className)}">(${escapeHtml(volume.text)} млн т)</span>
      </td>`;
    }

    _renderTable(rows, showFallout = false) {
      if (!this.hasTableWrapTarget) return;

      if (!rows.length) {
        this.tableWrapTarget.innerHTML =
          '<div class="text-muted py-4 text-center">Нет данных для таблицы.</div>';
        return;
      }

      const falloutHeader = showFallout
        ? '<th class="text-end" title="Δ дохода и объёма от эластичности спроса; «+» — рост, «−» — снижение">Δ эластичности</th>'
        : "";

      const body = rows
        .map((row) => {
          const rowClass = row.is_subtotal ? "fw-subtotal fw-bold" : "";
          const falloutCell = showFallout ? this._formatEffectsFalloutCell(row) : "";

          const basePct = this._formatSignedPct(row.base_pct);
          const rulesPct = this._formatSignedPct(row.rules_pct);
          const totalPct = this._formatSignedPct(row.total_pct);

          return `
            <tr class="${rowClass}">
              <td>${escapeHtml(row.label || "")}</td>
              <td class="text-end">
                ${escapeHtml(this._formatBlnFromRub(row.base_rub))}<br />
                <span class="cell-pct ${escapeHtml(basePct.className)}">${escapeHtml(basePct.text)}</span>
              </td>
              <td class="text-end">
                ${escapeHtml(this._formatBlnFromRub(row.rules_rub))}<br />
                <span class="cell-pct ${escapeHtml(rulesPct.className)}">${escapeHtml(rulesPct.text)}</span>
              </td>
              <td class="text-end">
                ${escapeHtml(this._formatBlnFromRub(row.total_rub))}<br />
                <span class="cell-pct ${escapeHtml(totalPct.className)}">${escapeHtml(totalPct.text)}</span>
              </td>
              ${falloutCell}
            </tr>
          `;
        })
        .join("");

      this.tableWrapTarget.innerHTML = `
        <div class="table-responsive">
          <table class="table table-sm table-vcenter">
            <thead>
              <tr>
                <th></th>
                <th class="text-end">Базовые решения</th>
                <th class="text-end">Отдельные решения</th>
                <th class="text-end">Увеличение нагрузки</th>
                ${falloutHeader}
              </tr>
            </thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;
    }

    _renderChart(chartData) {
      if (!this.hasChartCanvasTarget || typeof window.Chart === "undefined") {
        return;
      }

      this._destroyChart();

      const rawLabels = (chartData && chartData.labels) || [];
      const rawBase = ((chartData && chartData.base_bln) || []).map((v) =>
        Number(String(v).replace(",", ".")),
      );
      const rawRules = ((chartData && chartData.rules_bln) || []).map((v) =>
        Number(String(v).replace(",", ".")),
      );

      if (!rawLabels.length) {
        return;
      }

      const rows = rawLabels.map((label, index) => {
        const base = rawBase[index] || 0;
        const rules = rawRules[index] || 0;
        return { label, base, rules, total: base + rules };
      });
      rows.sort((a, b) => b.total - a.total);

      const labels = rows.map((row) => row.label);
      const baseValues = rows.map((row) => row.base);
      const rulesValues = rows.map((row) => row.rules);
      const totalValues = rows.map((row) => row.total);

      const ChartDataLabelsPlugin =
        window.ChartDataLabels || window.ChartDataLabelsPlugin || null;
      if (ChartDataLabelsPlugin && window.Chart) {
        window.Chart.register(ChartDataLabelsPlugin);
      }

      const ctx = this.chartCanvasTarget.getContext("2d");
      this.state.chart = new window.Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: "Базовые решения",
              data: baseValues,
              backgroundColor: "#003256",
              stack: "effects",
              datalabels: { display: false },
            },
            {
              label: "Отдельные решения",
              data: rulesValues,
              backgroundColor: "#4b8bc7",
              stack: "effects",
            },
          ],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          layout: {
            padding: { right: 56 },
          },
          scales: {
            x: {
              stacked: true,
              ticks: { display: false },
              grid: { display: false },
            },
            y: {
              stacked: true,
              grid: { display: false },
            },
          },
          plugins: {
            legend: {
              position: "bottom",
            },
            datalabels: {
              display(context) {
                return context.datasetIndex === context.chart.data.datasets.length - 1;
              },
              formatter(_value, context) {
                const total = totalValues[context.dataIndex];
                if (!Number.isFinite(total)) return "";
                return total.toFixed(1);
              },
              anchor: "end",
              align: "end",
              offset: 6,
              color: "#111827",
              font: { size: 11, weight: "600" },
              clip: false,
            },
          },
        },
      });
    }

    _destroyChart() {
      if (this.state.chart) {
        try {
          this.state.chart.destroy();
        } catch (_e) {
          // ignore
        }
        this.state.chart = null;
      }
    }

    _formatPct(value) {
      const num = Number(String(value).replace(",", "."));
      if (!Number.isFinite(num)) return "0.0";
      return num.toFixed(1);
    }

    _formatSignedPct(value) {
      const num = Number(String(value).replace(",", "."));
      if (!Number.isFinite(num)) {
        return { text: "(0.0%)", className: "" };
      }
      const abs = Math.abs(num).toFixed(1);
      if (num > 0) {
        return { text: `(+${abs}%)`, className: "is-positive" };
      }
      if (num < 0) {
        return { text: `(-${abs}%)`, className: "is-negative" };
      }
      return { text: "(0.0%)", className: "" };
    }

    _formatBlnFromRub(rubValue) {
      const num = Number(String(rubValue).replace(",", "."));
      if (!Number.isFinite(num)) return "0.0";
      return (num / 1_000_000_000).toFixed(1);
    }

    _absoluteGroupingIsDefault() {
      const revenuesGroupBy =
        this.revenuesGroupBySelectTarget?.value || "cargo_group";
      const revenuesInner =
        this.revenuesGroupByInnerSelectTarget?.value || "none";
      const volumesGroupBy =
        this.volumesGroupBySelectTarget?.value || "cargo_group";
      const volumesInner =
        this.volumesGroupByInnerSelectTarget?.value || "none";
      return (
        revenuesGroupBy === "cargo_group" &&
        revenuesInner === "none" &&
        volumesGroupBy === "cargo_group" &&
        volumesInner === "none"
      );
    }

    _canUseEarlyAbsolute(earlyGroupReady = this.state.earlyGroupReady) {
      return Boolean(earlyGroupReady) && this._absoluteGroupingIsDefault();
    }

    _needsFullCompactForAbsolute() {
      return !this._absoluteGroupingIsDefault();
    }

    async _refreshAbsoluteWhenCompactReady() {
      const ready = await this._ensureCompactReady();
      if (!ready) {
        return;
      }
      const tasks = [
        this._aggregateEffects({ showTableLoading: true }),
      ];
      if (this._absoluteGroupingIsDefault()) {
        tasks.push(this._aggregateRevenues(), this._aggregateVolumes());
      }
      await Promise.all(tasks);
    }

    _absolutePayload(kind) {
      const isRevenues = kind === "revenues";
      return {
        scenario_id: this.state.selectedScenarioId,
        cache_key: this.state.cacheKey,
        group_by: isRevenues
          ? this.revenuesGroupBySelectTarget?.value || "cargo_group"
          : this.volumesGroupBySelectTarget?.value || "cargo_group",
        group_by_inner: isRevenues
          ? this.revenuesGroupByInnerSelectTarget?.value || "none"
          : this.volumesGroupByInnerSelectTarget?.value || "none",
        include_fallout: this._includeFalloutForKind(kind),
      };
    }

    async _aggregateRevenues(options = {}) {
      return this._aggregateAbsoluteTable("revenues", options);
    }

    async _aggregateVolumes(options = {}) {
      return this._aggregateAbsoluteTable("volumes", options);
    }

    async _aggregateAbsoluteTable(kind, { attempt = 0 } = {}) {
      const isRevenues = kind === "revenues";
      const url = isRevenues ? this.revenuesUrlValue : this.volumesUrlValue;
      const wrapTarget = isRevenues
        ? this.revenuesTableWrapTarget
        : this.volumesTableWrapTarget;
      const hasTarget = isRevenues
        ? this.hasRevenuesTableWrapTarget
        : this.hasVolumesTableWrapTarget;
      const setLoading = (isLoading, message) => {
        if (isRevenues) {
          this._setRevenuesTableLoading(isLoading, message);
        } else {
          this._setVolumesTableLoading(isLoading, message);
        }
      };
      const errorLabel = isRevenues ? "выручки" : "объёмов";

      if (!url || !this.state.cacheKey || !this.state.selectedScenarioId) {
        return;
      }

      const includeFallout = this._includeFalloutForKind(kind);
      const needsCompactWait =
        (this.state.awaitingCompact || this.state.compactPending) &&
        (!this._canUseEarlyAbsolute() || includeFallout);
      const maxAttempts = needsCompactWait || includeFallout ? 45 : 5;
      const loadingMessage = includeFallout
        ? "Расчёт выпадения…"
        : needsCompactWait
          ? "Обновление детализации…"
          : "Расчёт данных…";

      if (attempt === 0 && includeFallout) {
        await this._ensureCompactReady();
      }

      if (attempt === 0 || needsCompactWait || includeFallout) {
        setLoading(true, loadingMessage);
      }

      try {
        const { response, data } = await fetchJson(url, {
          method: "POST",
          body: this._absolutePayload(kind),
        });

        if (!response.ok || !data || !data.success) {
          const message =
            (data && data.errors && data.errors.join("; ")) ||
            `Ошибка загрузки ${errorLabel}`;
          if (
            (needsCompactWait || includeFallout) &&
            attempt + 1 < maxAttempts
          ) {
            await this._waitForCompactReady();
            return this._aggregateAbsoluteTable(kind, {
              attempt: attempt + 1,
            });
          }
          if (
            this._isAggregatePendingMessage(message) &&
            attempt + 1 < maxAttempts
          ) {
            await this._sleep(2000);
            return this._aggregateAbsoluteTable(kind, {
              attempt: attempt + 1,
            });
          }
          this._showError(message);
          if (hasTarget) {
            setLoading(false);
            wrapTarget.innerHTML =
              '<div class="text-muted py-4 text-center">Нет данных.</div>';
          }
          return;
        }

        const rows = (data.table && data.table.rows) || [];
        if (
          (this._absoluteRowsLookEmpty(rows) || !rows.length) &&
          (needsCompactWait || includeFallout) &&
          attempt + 1 < maxAttempts
        ) {
          await this._waitForCompactReady();
          return this._aggregateAbsoluteTable(kind, { attempt: attempt + 1 });
        }

        this._renderAbsoluteTable(wrapTarget, data);
      } catch (error) {
        console.error(`[decision-effects] ${kind} aggregate failed`, error);
        if (attempt + 1 < maxAttempts) {
          await this._sleep(2000);
          return this._aggregateAbsoluteTable(kind, { attempt: attempt + 1 });
        }
        if (hasTarget) {
          setLoading(false);
          wrapTarget.innerHTML =
            '<div class="text-muted py-4 text-center">Не удалось загрузить таблицу.</div>';
        }
      }
    }

    _formatAbsoluteCell(value, fallout) {
      const main = escapeHtml(value || "0.00");
      if (!fallout) {
        return main;
      }
      const raw = String(fallout);
      const cls = raw.trim().startsWith("-") ? "text-danger" : "text-success";
      return `${main} <span class="decision-effects-fallout-hint ${cls}">(${escapeHtml(raw)})</span>`;
    }

    _absoluteRowsLookEmpty(rows) {
      if (!rows.length) {
        return true;
      }
      return !rows.some((row) => {
        const total = Number(String(row.total || "0").replace(",", "."));
        if (Number.isFinite(total) && Math.abs(total) > 0) {
          return true;
        }
        const yearValues = row.years || {};
        return Object.values(yearValues).some((value) => {
          const num = Number(String(value).replace(",", "."));
          return Number.isFinite(num) && Math.abs(num) > 0;
        });
      });
    }

    _renderAbsoluteTable(wrapEl, data) {
      if (!wrapEl) return;

      wrapEl.classList.remove("decision-effects-absolute-table-wrap--loading");

      const years = data.years || [];
      const rows = (data.table && data.table.rows) || [];
      const totalLabel = data.total_column_label || "Итого";
      const showFalloutAdjusted = Boolean(data.show_fallout_adjusted);

      if (!rows.length) {
        wrapEl.classList.remove(
          "decision-effects-absolute-table-wrap--loading",
        );
        wrapEl.innerHTML =
          '<div class="text-muted py-4 text-center">Нет данных.</div>';
        return;
      }

      const yearHeaders = years
        .map((year) => `<th class="text-end">${escapeHtml(String(year))}</th>`)
        .join("");

      const body = rows
        .map((row) => {
          const rowClass = row.is_subtotal ? "fw-subtotal fw-bold" : "";
          const yearCells = years
            .map((year) => {
              const value = (row.years && row.years[String(year)]) || "0.00";
              const fallout =
                showFalloutAdjusted &&
                row.years_fallout &&
                row.years_fallout[String(year)]
                  ? row.years_fallout[String(year)]
                  : null;
              return `<td class="text-end">${this._formatAbsoluteCell(value, fallout)}</td>`;
            })
            .join("");
          const totalFallout =
            showFalloutAdjusted && row.total_fallout ? row.total_fallout : null;
          return `
            <tr class="${rowClass}">
              <td>${escapeHtml(row.label || "")}</td>
              ${yearCells}
              <td class="text-end fw-bold">${this._formatAbsoluteCell(row.total || "0.00", totalFallout)}</td>
            </tr>
          `;
        })
        .join("");

      wrapEl.innerHTML = `
        <div class="table-responsive">
          <table class="table table-sm table-vcenter decision-effects-absolute-table">
            <thead>
              <tr>
                <th></th>
                ${yearHeaders}
                <th class="text-end">${escapeHtml(totalLabel)}</th>
              </tr>
            </thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;
    }

    async _exportAbsolute(kind) {
      const exportUrl =
        kind === "revenues"
          ? this.revenuesExportUrlValue
          : this.volumesExportUrlValue;
      if (!exportUrl || !this.state.cacheKey) return;

      try {
        const { response, blob } = await fetchBlob(exportUrl, {
          method: "POST",
          body: this._absolutePayload(kind),
        });

        if (!response.ok) {
          this._showError("Не удалось экспортировать таблицу.");
          return;
        }

        const disposition = response.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename="([^"]+)"/);
        const filename = match
          ? match[1]
          : kind === "revenues"
            ? "dohody_vsego.xlsx"
            : "obem_perevozok.xlsx";

        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch (error) {
        console.error("[decision-effects] export failed", error);
        this._showError("Не удалось экспортировать таблицу.");
      }
    }
  }

  application.register("decision-effects", DecisionEffectsController);
})();
