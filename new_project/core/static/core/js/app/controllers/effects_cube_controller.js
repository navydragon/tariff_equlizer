import { fetchBlob, fetchJson } from "../lib/http.js";
import { escapeHtml } from "../lib/dom.js";
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
    ];

    static values = {
      scenariosUrl: String,
      computeUrl: String,
      computePandasUrl: String,
      warmStatusUrl: String,
      compactStatusUrl: String,
      cubeUrl: String,
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
        suppressFilterEvents: false,
        computing: false,
        compactPending: false,
        groupByInnerLabel: null,
        groupByLabel: "Группа груза",
      };

      this._onTariffRulesChanged = this._onTariffRulesChanged.bind(this);
      document.addEventListener("tariff-rules-changed", this._onTariffRulesChanged);

      this._loadScenarios();
    }

    disconnect() {
      document.removeEventListener("tariff-rules-changed", this._onTariffRulesChanged);
      this._destroyTomSelects();
    }

    onScenarioChange() {
      const raw = this.hasScenarioSelectTarget
        ? this.scenarioSelectTarget.value
        : "";
      this.state.selectedScenarioId = raw ? Number(raw) : null;
      this.state.cacheKey = null;
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
        this._aggregateCube();
      }, this.debounceMsValue || 350);
    }

    onExport() {
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

    _onTariffRulesChanged(event) {
      const scenarioId = event?.detail?.scenarioId;
      if (
        scenarioId &&
        this.state.selectedScenarioId &&
        Number(scenarioId) === Number(this.state.selectedScenarioId)
      ) {
        this.state.cacheKey = null;
        this._computeEffects();
      }
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
        if (data.kpi_ready || data.phase === "done") {
          return;
        }
        await this._sleep(300);
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
        await this._sleep(2000);
        return;
      }

      try {
        const { data } = await fetchJson(this.compactStatusUrlValue, {
          method: "POST",
          body: { cache_key: this.state.cacheKey },
        });
        if (data && data.success) {
          this.state.compactPending = !data.compact_ready;
        }
      } catch (error) {
        console.error("[effects-cube] compact-status failed", error);
      }
      await this._sleep(2000);
    }

    async _computeEffects() {
      const computeUrl = this._resolveComputeUrl();
      if (!computeUrl || !this.state.selectedScenarioId) return;

      this._clearToasts();
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

    async _aggregateCube({ showTableLoading = false, attempt = 0 } = {}) {
      if (
        !this.cubeUrlValue ||
        !this.state.selectedScenarioId ||
        !this.state.cacheKey
      ) {
        return;
      }

      if (showTableLoading && attempt === 0) {
        this._setTableLoading(true, "Загрузка таблицы…");
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
            this.state.cacheKey = null;
            this._computeEffects();
            return;
          }
          if (this.state.compactPending && attempt + 1 < maxAttempts) {
            await this._waitForCompactReady();
            return this._aggregateCube({
              showTableLoading,
              attempt: attempt + 1,
            });
          }
          if (this._isCubePendingMessage(message) && attempt + 1 < maxAttempts) {
            await this._sleep(2000);
            return this._aggregateCube({
              showTableLoading,
              attempt: attempt + 1,
            });
          }
          this._setTableMessage("Нет данных.");
          this._showError(message);
          return;
        }

        this.state.compactPending = false;
        this.state.groupByLabel = data.group_by_label || this.state.groupByLabel;
        this.state.groupByInnerLabel = data.group_by_inner_label;
        this._renderCubeTable(data);
      } catch (error) {
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

    _setTableLoading(isLoading, message = "Загрузка…") {
      if (!this.hasTableWrapTarget) return;
      this.tableWrapTarget.classList.toggle(
        "effects-cube-table-wrap--loading",
        isLoading,
      );
      if (isLoading) {
        this.tableWrapTarget.innerHTML = `<div class="text-muted py-4 text-center">${escapeHtml(message)}</div>`;
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
      if (!this.exportUrlValue || !this.state.cacheKey) return;

      try {
        const { response, blob } = await fetchBlob(this.exportUrlValue, {
          method: "POST",
          body: this._cubePayload(),
        });

        if (!response.ok) {
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
      } catch (error) {
        console.error("[effects-cube] export failed", error);
        this._showError("Не удалось экспортировать таблицу.");
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

    _renderWarning(routesWithoutCharge, routesWithoutVolume, meta = {}) {
      const chargeCount = Number(routesWithoutCharge) || 0;
      const volumeCount = Number(routesWithoutVolume) || 0;

      if (meta.elapsed_ms != null) {
        showToast(
          `Расчёт выполнен за ${meta.elapsed_ms} мс.`,
          this._toastOptions({
            variant: "info",
            title: "Готово",
            delay: 7000,
          }),
        );
      }

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

    _clearToasts() {
      clearToasts(
        this.hasToastContainerTarget ? this.toastContainerTarget : undefined,
      );
    }
  }

  application.register("effects-cube", EffectsCubeController);
})();
