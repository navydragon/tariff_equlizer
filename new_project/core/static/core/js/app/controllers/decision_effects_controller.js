import { fetchBlob, fetchJson } from "../lib/http.js";
import { escapeHtml } from "../lib/dom.js";
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
      "engineSelect",
      "kpiCards",
      "groupBySelect",
      "groupByInnerSelect",
      "cargoFilterSelect",
      "holdingFilterSelect",
      "yearSelect",
      "tableWrap",
      "chartCanvas",
      "toastContainer",
      "revenuesGroupBySelect",
      "revenuesGroupByInnerSelect",
      "revenuesTableWrap",
      "volumesGroupBySelect",
      "volumesGroupByInnerSelect",
      "volumesTableWrap",
    ];

    static values = {
      scenariosUrl: String,
      computeUrl: String,
      computePandasUrl: String,
      aggregateUrl: String,
      revenuesUrl: String,
      volumesUrl: String,
      revenuesExportUrl: String,
      volumesExportUrl: String,
      activeScenarioId: String,
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
        computeEngine: this.hasEngineSelectTarget
          ? this.engineSelectTarget.value || "pandas"
          : "pandas",
      };

      this._loadScenarios();
    }

    disconnect() {
      this._destroyChart();
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

    onEngineChange() {
      if (this.hasEngineSelectTarget) {
        this.state.computeEngine = this.engineSelectTarget.value || "pandas";
      }
      this.state.cacheKey = null;
      this._computeEffects();
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
      if (
        this.state.computeEngine === "pandas" &&
        this.computePandasUrlValue
      ) {
        return this.computePandasUrlValue;
      }
      return this.computeUrlValue;
    }

    async _computeEffects() {
      const computeUrl = this._resolveComputeUrl();
      if (!computeUrl || !this.state.selectedScenarioId) return;

      this._clearToasts();
      this._setKpiLoading(true);
      this._setRevenuesTableLoading(true, "Расчёт данных…");
      this._setVolumesTableLoading(true, "Расчёт данных…");
      this.state.computing = true;

      try {
        const { response, data } = await fetchJson(computeUrl, {
          method: "POST",
          body: { scenario_id: this.state.selectedScenarioId },
        });

        if (!response.ok || !data || !data.success) {
          this.state.cacheKey = null;
          this._renderKpiCards([]);
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
        this.state.scenarioYears = data.years || [];
        this._renderWarning(
          data.routes_without_charge,
          data.routes_without_volume,
          {
            engine: data.engine,
            elapsed_ms: data.elapsed_ms,
            timings: data.timings,
          },
        );
        this._syncYearOptions(data.years || []);
        this._syncFilterOptions(data.filter_options || {});
        this._renderKpiCards(data.cards || []);

        await Promise.all([
          this._aggregateEffects({ showTableLoading: true }),
          this._aggregateRevenues(),
          this._aggregateVolumes(),
        ]);
      } catch (error) {
        console.error("[decision-effects] compute failed", error);
        this.state.cacheKey = null;
        this._renderKpiCards([]);
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

    async _aggregateEffects({ showTableLoading = false } = {}) {
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

      if (showTableLoading) {
        this._setTableLoading(true);
      }

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
          this._showError(message);
          return;
        }

        this._renderTable(data.table && data.table.rows ? data.table.rows : []);
        this._renderChart(data.chart || null);
      } catch (error) {
        console.error("[decision-effects] aggregate failed", error);
        this._showError("Не удалось обновить таблицу и график.");
      } finally {
        if (showTableLoading) {
          this._setTableLoading(false);
        }
      }
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

    _renderWarning(skippedCharge, skippedVolume, meta = {}) {
      const chargeCount = Number(skippedCharge) || 0;
      const volumeCount = Number(skippedVolume) || 0;

      if (meta.engine) {
        const elapsed =
          meta.elapsed_ms === undefined || meta.elapsed_ms === null
            ? ""
            : `, ${meta.elapsed_ms} мс`;
        let timingDetails = "";
        if (meta.timings) {
          const partsTiming = [
            ["загрузка", meta.timings.load_ms],
            ["расчёт", meta.timings.compute_ms],
            ["кэш", meta.timings.cache_ms],
            ["stats", meta.timings.stats_ms],
            ["sql", meta.timings.routes_sql_execute_ms],
            ["fetch", meta.timings.routes_fetch_ms],
            ["df", meta.timings.dataframe_build_ms],
          ]
            .filter(([, value]) => value !== undefined && value !== null)
            .map(([label, value]) => `${label} ${value} мс`);
          if (partsTiming.length) {
            timingDetails = ` (${partsTiming.join(", ")})`;
          }
        }
        if (meta.cache_hit) {
          timingDetails += ", снимок сценария";
        }
        showToast(
          `Движок расчёта: ${meta.engine}${elapsed}${timingDetails}.`,
          this._toastOptions({
            variant: "info",
            title: "Расчёт выполнен",
            delay: 7000,
          }),
        );
      }

      const warnings = [];
      if (chargeCount > 0) {
        warnings.push(
          `${chargeCount} маршрут(ов) без провозной платы не учтены в расчёте доходов.`,
        );
      }
      if (volumeCount > 0) {
        warnings.push(
          `${volumeCount} маршрут(ов) без объёма перевозок не учтены в блоке объёмов.`,
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

      this.kpiCardsTarget.innerHTML = cards
        .map((card) => {
          const totalPct = this._formatPct(card.total_pct);
          const basePct = this._formatPct(card.base_pct);
          const rulesPct = this._formatPct(card.rules_pct);
          return `
            <article class="decision-effects-kpi-card">
              <div class="decision-effects-kpi-card__year">${escapeHtml(String(card.year))} год</div>
              <div class="decision-effects-kpi-card__body">
                <div class="decision-effects-kpi-card__info">
                  <div class="decision-effects-kpi-card__count">
                    <span class="decision-effects-kpi-card__total-value">${escapeHtml(card.total_bln)}</span>
                    <span class="decision-effects-kpi-card__total-unit">млрд</span>
                  </div>
                  <p class="decision-effects-kpi-card__total-caption">
                    Индексация<span class="decision-effects-kpi-card__total-caption-pct"> (${escapeHtml(totalPct)}%)</span>
                  </p>
                </div>
                <div class="decision-effects-kpi-card__split">
                  <div class="decision-effects-kpi-card__split-item">
                    <div class="decision-effects-kpi-card__count">
                      <span class="decision-effects-kpi-card__split-value">${escapeHtml(card.base_bln)}</span>
                      <span class="decision-effects-kpi-card__split-unit">млрд</span>
                    </div>
                    <div class="decision-effects-kpi-card__split-meta">
                      <span class="decision-effects-kpi-card__split-label">Базовые решения</span>
                      <span class="decision-effects-kpi-card__split-pct">(+${escapeHtml(basePct)}%)</span>
                    </div>
                  </div>
                  <div class="decision-effects-kpi-card__split-item">
                    <div class="decision-effects-kpi-card__count">
                      <span class="decision-effects-kpi-card__split-value">${escapeHtml(card.rules_bln)}</span>
                      <span class="decision-effects-kpi-card__split-unit">млрд</span>
                    </div>
                    <div class="decision-effects-kpi-card__split-meta">
                      <span class="decision-effects-kpi-card__split-label">Отдельные решения</span>
                      <span class="decision-effects-kpi-card__split-pct">(+${escapeHtml(rulesPct)}%)</span>
                    </div>
                  </div>
                </div>
              </div>
            </article>          `;
        })
        .join("");
    }

    _renderTable(rows) {
      if (!this.hasTableWrapTarget) return;

      if (!rows.length) {
        this.tableWrapTarget.innerHTML =
          '<div class="text-muted py-4 text-center">Нет данных для таблицы.</div>';
        return;
      }

      const body = rows
        .map((row) => {
          const rowClass = row.is_subtotal ? "fw-subtotal fw-bold" : "";
          return `
            <tr class="${rowClass}">
              <td>${escapeHtml(row.label || "")}</td>
              <td class="text-end">
                ${escapeHtml(this._formatBlnFromThs(row.base_ths_rub))}<br />
                <span class="cell-pct">(+${escapeHtml(this._formatPct(row.base_pct))}%)</span>
              </td>
              <td class="text-end">
                ${escapeHtml(this._formatBlnFromThs(row.rules_ths_rub))}<br />
                <span class="cell-pct">(+${escapeHtml(this._formatPct(row.rules_pct))}%)</span>
              </td>
              <td class="text-end">
                ${escapeHtml(this._formatBlnFromThs(row.total_ths_rub))}<br />
                <span class="cell-pct">(+${escapeHtml(this._formatPct(row.total_pct))}%)</span>
              </td>
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

      const labels = (chartData && chartData.labels) || [];
      const baseValues = ((chartData && chartData.base_bln) || []).map((v) =>
        Number(String(v).replace(",", ".")),
      );
      const rulesValues = ((chartData && chartData.rules_bln) || []).map((v) =>
        Number(String(v).replace(",", ".")),
      );

      if (!labels.length) {
        return;
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

    _formatBlnFromThs(thsValue) {
      const num = Number(String(thsValue).replace(",", "."));
      if (!Number.isFinite(num)) return "0.0";
      return (num / 1_000_000).toFixed(1);
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
      };
    }

    async _aggregateRevenues() {
      if (
        !this.revenuesUrlValue ||
        !this.state.cacheKey ||
        !this.state.selectedScenarioId
      ) {
        return;
      }

      this._setRevenuesTableLoading(true);

      try {
        const { response, data } = await fetchJson(this.revenuesUrlValue, {
          method: "POST",
          body: this._absolutePayload("revenues"),
        });

        if (!response.ok || !data || !data.success) {
          if (this.hasRevenuesTableWrapTarget) {
            this._setAbsoluteTableLoading(
              this.revenuesTableWrapTarget,
              false,
            );
            this.revenuesTableWrapTarget.innerHTML =
              '<div class="text-muted py-4 text-center">Нет данных.</div>';
          }
          return;
        }

        this._renderAbsoluteTable(
          this.revenuesTableWrapTarget,
          data,
        );
      } catch (error) {
        console.error("[decision-effects] revenues aggregate failed", error);
        if (this.hasRevenuesTableWrapTarget) {
          this._setAbsoluteTableLoading(this.revenuesTableWrapTarget, false);
          this.revenuesTableWrapTarget.innerHTML =
            '<div class="text-muted py-4 text-center">Не удалось загрузить таблицу.</div>';
        }
      }
    }

    async _aggregateVolumes() {
      if (
        !this.volumesUrlValue ||
        !this.state.cacheKey ||
        !this.state.selectedScenarioId
      ) {
        return;
      }

      this._setVolumesTableLoading(true);

      try {
        const { response, data } = await fetchJson(this.volumesUrlValue, {
          method: "POST",
          body: this._absolutePayload("volumes"),
        });

        if (!response.ok || !data || !data.success) {
          if (this.hasVolumesTableWrapTarget) {
            this._setAbsoluteTableLoading(this.volumesTableWrapTarget, false);
            this.volumesTableWrapTarget.innerHTML =
              '<div class="text-muted py-4 text-center">Нет данных.</div>';
          }
          return;
        }

        this._renderAbsoluteTable(this.volumesTableWrapTarget, data);
      } catch (error) {
        console.error("[decision-effects] volumes aggregate failed", error);
        if (this.hasVolumesTableWrapTarget) {
          this._setAbsoluteTableLoading(this.volumesTableWrapTarget, false);
          this.volumesTableWrapTarget.innerHTML =
            '<div class="text-muted py-4 text-center">Не удалось загрузить таблицу.</div>';
        }
      }
    }

    _renderAbsoluteTable(wrapEl, data) {
      if (!wrapEl) return;

      wrapEl.classList.remove("decision-effects-absolute-table-wrap--loading");

      const years = data.years || [];
      const rows = (data.table && data.table.rows) || [];
      const totalLabel = data.total_column_label || "Итого";

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
              return `<td class="text-end">${escapeHtml(value)}</td>`;
            })
            .join("");
          return `
            <tr class="${rowClass}">
              <td>${escapeHtml(row.label || "")}</td>
              ${yearCells}
              <td class="text-end fw-bold">${escapeHtml(row.total || "0.00")}</td>
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
