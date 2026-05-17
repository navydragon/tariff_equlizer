import { fetchJson } from "../lib/http.js";
import { escapeHtml, setVisible } from "../lib/dom.js";

(function () {
  // eslint-disable-next-line no-console
  console.info("[route-analysis] controller module loaded");

  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error(
      "Stimulus application is not initialized for route-analysis-route-picker.",
    );
    return;
  }

  class RouteAnalysisRoutePickerController extends Stimulus.Controller {
    static targets = [
      "scenarioSelect",
      "searchInput",
      "routeList",
      "loading",
      "empty",
      "errors",
      "confirmButton",
      "diagramTypeSelect",
      "diagramPlaceholder",
      "equalizerTypeSelect",
      "equalizerPanel",
      "equalizerEmpty",
      "equalizerControls",
      "equalizerUnitHint",
    ];

    static values = {
      scenariosUrl: String,
      routesUrl: String,
      routeAnalysisUrl: String,
      activeScenarioId: String,
      pageSize: { type: Number, default: 20 },
      searchDebounceMs: { type: Number, default: 400 },
    };

    connect() {
      // eslint-disable-next-line no-console
      console.info("[route-analysis] controller connected", this.element);
      const dbg = document.getElementById("routeAnalysisDebug");
      if (dbg) {
        dbg.textContent = "route-analysis-route-picker: connected";
      }

      this.state = {
        modal: null,
        modalEl: null,
        boundSearchHandler: null,
        boundConfirmHandler: null,
        searchTimeout: null,
        routesRequestInFlight: null,
        scenarioById: new Map(),
        selectedScenario: null,
        selectedScenarioId: null,
        selectedRouteSetId: null,
        pendingSelectedRoute: null,
        selectedRoute: null,
        trendsChart: null,
        routeAnalysisCache: new Map(),
        activeCalculateData: null,
        equalizerBaseline: null,
        equalizerOverrides: {},
        equalizerDebounceTimer: null,
        equalizerRecalcInFlight: false,
      };

      this.state.modalEl = document.getElementById("routeAnalysisRouteModal");
      if (this.state.modalEl && typeof bootstrap !== "undefined") {
        this.state.modal =
          bootstrap.Modal.getInstance(this.state.modalEl) ||
          bootstrap.Modal.getOrCreateInstance(this.state.modalEl);
      }
      this.state.boundSearchHandler = this.onSearchInput.bind(this);

      this._resetUi();
      this._renderRouteDetails(null);
      this._updateEqualizerVisibility(false);

      // Загружаем сценарии сразу при открытии страницы, чтобы верхний select
      // не был пустым и не зависел от открытия модалки.
      this._renderScenarioLoadingPlaceholder();
      this._initScenariosOnPage();

      // Инициализируем заглушку диаграмм.
      this._renderDiagram();
    }

    onDiagramTypeChange() {
      this._renderDiagram();
    }

    async openModal() {
      this._resetUi();
      if (this.state.modal) {
        this.state.modal.show();
      }
      this._ensureModalHandlers();
      const input = this._getSearchInputEl();
      if (input) input.focus();
    }

    onScenarioChange() {
      const raw = this.hasScenarioSelectTarget
        ? this.scenarioSelectTarget.value
        : "";
      const scenarioId = raw ? Number(raw) : null;
      this.state.routeAnalysisCache.clear();
      this._setScenario(scenarioId);
      this._resetRouteSearch();
      this._renderRouteDetails(null);
      this.state.selectedRoute = null;
      this._resetEqualizer();
      this._renderDiagram();
    }

    onSearchInput() {
      clearTimeout(this.state.searchTimeout);
      // eslint-disable-next-line no-console
      console.info("[route-analysis] onSearchInput", {
        selectedScenarioId: this.state.selectedScenarioId,
        selectedRouteSetId: this.state.selectedRouteSetId,
        query: this._getSearchInputEl() ? this._getSearchInputEl().value : "",
      });
      this.state.searchTimeout = setTimeout(() => {
        this._loadRoutes({
          search: this._getSearchInputEl() ? this._getSearchInputEl().value : "",
          page: 1,
        });
      }, this.searchDebounceMsValue || 400);
    }

    async confirmSelection() {
      // eslint-disable-next-line no-console
      console.info("[route-analysis] confirmSelection", {
        hasPending: !!this.state.pendingSelectedRoute,
      });
      if (!this.state.pendingSelectedRoute) return;
      this.state.selectedRoute = this.state.pendingSelectedRoute;
      this._renderRouteDetails(this.state.selectedRoute);
      if (this.state.modal) {
        this.state.modal.hide();
      }

      this.state.routeAnalysisCache.clear();
      this.state.equalizerOverrides = {};
      await this._loadEqualizerBaseline();
      this._renderDiagram();
    }

    onEqualizerTypeChange() {
      this._renderEqualizerPanel();
    }

    async _loadScenarios() {
      if (!this.scenariosUrlValue) return;

      this._showErrors([]);
      this._renderScenarioLoadingPlaceholder();
      const { data } = await fetchJson(this.scenariosUrlValue);
      if (!data || !data.success) {
        this._showErrors((data && data.errors) || ["Ошибка загрузки сценариев"]);
        return;
      }

      const scenarios = data.scenarios || [];
      this.state.scenarioById = new Map(
        scenarios.map((s) => [Number(s.id), s]),
      );

      if (this.hasScenarioSelectTarget) {
        this.scenarioSelectTarget.innerHTML = "";
        if (scenarios.length === 0) {
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "Нет доступных сценариев";
          this.scenarioSelectTarget.appendChild(opt);
          this._setScenario(null);
          return;
        }
        for (const s of scenarios) {
          const opt = document.createElement("option");
          opt.value = String(s.id);
          opt.textContent = s.name || `Сценарий #${s.id}`;
          this.scenarioSelectTarget.appendChild(opt);
        }
      }
    }

    _selectDefaultScenario() {
      const activeId = this._parseActiveScenarioId();
      const fallbackId = this._firstScenarioId();
      const scenarioId = activeId || fallbackId;

      if (this.hasScenarioSelectTarget && scenarioId != null) {
        this.scenarioSelectTarget.value = String(scenarioId);
      }
      this._setScenario(scenarioId);
      this._resetRouteSearch();
    }

    async _initScenariosOnPage() {
      try {
        await this._loadScenarios();
        this._selectDefaultScenario();
        this._renderDiagram();
      } catch (e) {
        this._showErrors(["Ошибка инициализации сценариев (см. консоль)"]);
        // eslint-disable-next-line no-console
        console.error("route-analysis-route-picker init failed", e);
      }
    }

    _renderScenarioLoadingPlaceholder() {
      if (!this.hasScenarioSelectTarget) return;
      if (this.scenarioSelectTarget.options.length > 0) return;
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Загрузка…";
      this.scenarioSelectTarget.appendChild(opt);
    }

    _parseActiveScenarioId() {
      const raw = (this.activeScenarioIdValue || "").trim();
      if (!raw) return null;
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    }

    _firstScenarioId() {
      for (const id of this.state.scenarioById.keys()) {
        return id;
      }
      return null;
    }

    _setScenario(scenarioId) {
      this.state.selectedScenarioId = scenarioId;
      this.state.pendingSelectedRoute = null;
      this._setConfirmEnabled(false);

      const s =
        scenarioId != null ? this.state.scenarioById.get(scenarioId) : null;
      this.state.selectedScenario = s || null;
      const routeSetId = s && s.route_set_id != null ? Number(s.route_set_id) : null;
      this.state.selectedRouteSetId =
        routeSetId && !Number.isNaN(routeSetId) ? routeSetId : null;
    }

    _resetRouteSearch() {
      if (this.hasSearchInputTarget) {
        this.searchInputTarget.value = "";
      }
      if (this.hasRouteListTarget) {
        this.routeListTarget.innerHTML = "";
      }
      if (this.hasEmptyTarget) setVisible(this.emptyTarget, false);
      this._setLoading(false);
    }

    async _loadRoutes({ search, page }) {
      if (!this.routesUrlValue) return;
      if (!this.state.selectedRouteSetId) {
        this._showErrors(["У выбранного сценария не задан набор маршрутов"]);
        // eslint-disable-next-line no-console
        console.warn("[route-analysis] skip routes fetch: route_set_id is empty");
        return;
      }

      // eslint-disable-next-line no-console
      console.info("[route-analysis] fetching routes", {
        routeSetId: this.state.selectedRouteSetId,
        search: (search || "").trim(),
        page: page || 1,
      });

      const query = new URLSearchParams();
      query.set("route_set_id", String(this.state.selectedRouteSetId));
      query.set("search", (search || "").trim());
      query.set("page", String(page || 1));
      query.set("page_size", String(this.pageSizeValue || 20));

      const url = `${this.routesUrlValue}?${query.toString()}`;
      const requestToken = {};
      this.state.routesRequestInFlight = requestToken;

      this._showErrors([]);
      this._setLoading(true);

      const { data } = await fetchJson(url);
      if (this.state.routesRequestInFlight !== requestToken) return;

      if (!data || !data.success) {
        this._showErrors((data && data.errors) || ["Ошибка загрузки маршрутов"]);
        this._setLoading(false);
        return;
      }

      const items = data.items || [];
      this._renderRouteList(items);
      this._setLoading(false);
    }

    _renderRouteList(items) {
      const listEl = this._getRouteListEl();
      if (!listEl) return;
      listEl.innerHTML = "";

      const emptyEl = this._getEmptyEl();
      if (emptyEl) setVisible(emptyEl, items.length === 0);
      this.state.pendingSelectedRoute = null;
      this._setConfirmEnabled(false);

      for (const route of items) {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "list-group-item list-group-item-action text-start";

        const cargo = route.cargo_name || "";
        const origin = route.origin_station_name || "";
        const destination = route.destination_station_name || "";
        const msgType = route.message_type_name || "";
        const routeCode = route.route_code || "";

        el.innerHTML = `
          <div class="d-flex w-100 justify-content-between gap-2">
            <div>
              <div class="fw-medium">${escapeHtml(routeCode)}</div>
              <div class="text-muted small">${escapeHtml(cargo)}</div>
              <div class="text-muted small">${escapeHtml(origin)} → ${escapeHtml(destination)}</div>
            </div>
            <div class="text-muted small text-end">${escapeHtml(msgType)}</div>
          </div>
        `;

        el.addEventListener("click", () => {
          for (const btn of listEl.querySelectorAll("button")) {
            btn.classList.remove("active");
          }
          el.classList.add("active");
          this.state.pendingSelectedRoute = route;
          this._setConfirmEnabled(true);
        });

        listEl.appendChild(el);
      }
    }

    _renderRouteDetails(route) {
      const detailsEl = document.getElementById("routeAnalysisRouteDetails");
      if (!detailsEl) return;

      if (!route) {
        detailsEl.innerHTML = `
          <div class="text-muted">
            Маршрут не выбран.
          </div>
        `;
        return;
      }

      const routeCode = (route.route_code || "").trim();
      const cargo = (route.cargo_name || "").trim();
      const origin = (route.origin_station_name || "").trim();
      const destination = (route.destination_station_name || "").trim();
      const msgType = (route.message_type_name || "").trim();
      const wagonKind = (route.wagon_kind_name || "").trim();
      const shipmentType = (route.shipment_type_name || "").trim();

      const pill = (text, icon) => {
        if (!text) return "";
        return `
          <span class="badge bg-azure-lt text-azure me-2 mb-2">
            <i class="ti ${escapeHtml(icon)} me-1"></i>
            ${escapeHtml(text)}
          </span>
        `;
      };

      const row = (label, value, icon) => {
        if (!value) return "";
        return `
          <div class="d-flex align-items-start gap-2 mb-2">
            <div class="text-muted" style="width: 140px;">
              <i class="ti ${escapeHtml(icon)} me-1"></i>
              ${escapeHtml(label)}
            </div>
            <div class="fw-medium text-body flex-grow-1">
              ${escapeHtml(value)}
            </div>
          </div>
        `;
      };

      detailsEl.classList.remove("text-muted");
      detailsEl.innerHTML = `
        <div class="border rounded-3 p-3 bg-light-subtle">
          <div class="d-flex align-items-start justify-content-between gap-2">
            <div>
              <div class="text-muted small mb-1">Код маршрута</div>
              <div class="fw-bold">${escapeHtml(routeCode || "—")}</div>
            </div>
            <div class="text-end">
              ${pill(msgType, "ti-message")}
            </div>
          </div>

          ${cargo ? `<div class="mt-3">${row("Груз", cargo, "ti-box")}</div>` : ""}

          <div class="mt-2">
            ${row("Отправление", origin, "ti-map-pin")}
            ${row("Назначение", destination, "ti-flag")}
          </div>

          <div class="mt-2">
            ${row("Род вагона", wagonKind, "ti-truck")}
            ${row("Тип отправки", shipmentType, "ti-send")}
          </div>
        </div>
      `;
    }

    async _renderDiagram() {
      const chartWrapEl = document.getElementById("routeAnalysisTrendsChartWrap");
      const chartCanvas = document.getElementById("routeAnalysisTrendsChart");
      const tableWrapEl = document.getElementById(
        "routeAnalysisStructureTableWrap",
      );
      const effectsWrapEl = document.getElementById("routeAnalysisEffectsTableWrap");
      const kpiWrapEl = document.getElementById("routeAnalysisKpiWrap");
      const placeholderEl =
        this.hasDiagramPlaceholderTarget
          ? this.diagramPlaceholderTarget
          : document.getElementById("routeAnalysisDiagramPlaceholder");

      const typeSelect =
        this.hasDiagramTypeSelectTarget ? this.diagramTypeSelectTarget : null;
      const typeValue = typeSelect ? typeSelect.value : "trends";

      const showPlaceholder = (html) => {
        this._hideDiagramExtras();
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (effectsWrapEl) {
          effectsWrapEl.style.display = "none";
          effectsWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) {
          kpiWrapEl.style.display = "none";
          kpiWrapEl.innerHTML = "";
        }
        if (this.state.trendsChart) {
          try {
            this.state.trendsChart.destroy();
          } catch (_e) {
            // ignore
          }
          this.state.trendsChart = null;
        }
        if (placeholderEl) {
          placeholderEl.style.display = "";
          placeholderEl.innerHTML = html;
        }
      };

      const showChart = () => {
        this._hideDiagramExtras();
        if (placeholderEl) placeholderEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (effectsWrapEl) {
          effectsWrapEl.style.display = "none";
          effectsWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) {
          kpiWrapEl.style.display = "none";
          kpiWrapEl.innerHTML = "";
        }
        if (chartWrapEl) chartWrapEl.style.display = "";
      };

      const showTable = () => {
        this._hideDiagramExtras();
        if (placeholderEl) placeholderEl.style.display = "none";
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (effectsWrapEl) {
          effectsWrapEl.style.display = "none";
          effectsWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) {
          kpiWrapEl.style.display = "none";
          kpiWrapEl.innerHTML = "";
        }
        if (tableWrapEl) tableWrapEl.style.display = "";
      };

      const showEffects = () => {
        this._hideDiagramExtras();
        if (placeholderEl) placeholderEl.style.display = "none";
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) {
          kpiWrapEl.style.display = "none";
          kpiWrapEl.innerHTML = "";
        }
        if (effectsWrapEl) effectsWrapEl.style.display = "";
      };

      const showKpi = () => {
        this._hideDiagramExtras();
        if (placeholderEl) placeholderEl.style.display = "none";
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (effectsWrapEl) {
          effectsWrapEl.style.display = "none";
          effectsWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) kpiWrapEl.style.display = "";
      };

      if (!this.state.selectedRoute) {
        showPlaceholder(`
          <div class="mb-2">
            <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
          </div>
          <div>Выберите маршрут для отображения диаграммы</div>
        `);
        return;
      }

      if (typeValue === "structure_table") {
        const scenarioId = this.state.selectedScenarioId;
        const routeId = this.state.selectedRoute ? this.state.selectedRoute.id : null;

        if (!scenarioId || !routeId) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Не удалось определить сценарий и маршрут для построения таблицы.</div>
          `);
          return;
        }

        showTable();
        await this._renderStructureTable({
          scenarioId,
          routeId,
          containerEl: tableWrapEl,
        });
        return;
      }

      if (typeValue === "decision_effects") {
        showEffects();
        if (effectsWrapEl) {
          effectsWrapEl.innerHTML = `
            <div class="text-center text-muted py-4">
              <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
              <div class="mt-2">Расчёт эффектов…</div>
            </div>
          `;
        }
        const result = await this._fetchRouteAnalysisData({});
        if (!result.ok) {
          showPlaceholder(`
            <div class="alert alert-danger" role="alert">
              ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
            </div>
          `);
          return;
        }
        showEffects();
        this._renderEffectsTable(effectsWrapEl, result.data);
        return;
      }

      if (typeValue === "kpi") {
        showKpi();
        if (kpiWrapEl) {
          kpiWrapEl.innerHTML = `
            <div class="text-center text-muted py-4 w-100">
              <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
              <div class="mt-2">Расчёт KPI…</div>
            </div>
          `;
        }
        const result = await this._fetchRouteAnalysisData({});
        if (!result.ok) {
          showPlaceholder(`
            <div class="alert alert-danger" role="alert">
              ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
            </div>
          `);
          return;
        }
        showKpi();
        this._renderKpiCards(kpiWrapEl, result.data);
        return;
      }

      if (!chartCanvas) return;
      if (typeof window.Chart === "undefined") {
        showPlaceholder(`
          <div class="mb-2">
            <i class="ti ti-alert-triangle" style="font-size: 2rem;"></i>
          </div>
          <div>Chart.js не загружен. Обновите страницу.</div>
        `);
        return;
      }

      const scenario = this.state.selectedScenario;
      const startYear = scenario && scenario.start_year ? Number(scenario.start_year) : null;
      const endYear = scenario && scenario.end_year ? Number(scenario.end_year) : null;
      if (!startYear || !endYear || Number.isNaN(startYear) || Number.isNaN(endYear)) {
        showPlaceholder(`
          <div class="mb-2">
            <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
          </div>
          <div>Не удалось определить годы сценария для построения графика.</div>
        `);
        return;
      }

      const years = [];
      for (let y = startYear; y <= endYear; y += 1) years.push(y);

      const toNum = (val) => {
        if (val == null) return null;
        const n = Number(String(val).replace(",", "."));
        return Number.isFinite(n) ? n : null;
      };

      const formatBox = (num) =>
        String(Math.round(num)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

      showChart();

      // eslint-disable-next-line no-undef
      const ChartDataLabelsPlugin =
        window.ChartDataLabels || window.ChartDataLabelsPlugin || null;
      if (ChartDataLabelsPlugin && window.Chart) {
        // eslint-disable-next-line no-undef
        window.Chart.register(ChartDataLabelsPlugin);
      }

      if (this.state.trendsChart) {
        try {
          this.state.trendsChart.destroy();
        } catch (_e) {
          // ignore
        }
        this.state.trendsChart = null;
      }

      const ctx = chartCanvas.getContext("2d");

      const commonPlugins = {
        legend: {
          position: "bottom",
          labels: {
            boxWidth: 18,
            boxHeight: 10,
          },
        },
        tooltip: {
          enabled: true,
          mode: "index",
          intersect: false,
          axis: "x",
        },
      };

      const commonInteraction = {
        mode: "index",
        intersect: false,
      };

      if (typeValue === "trends") {
        const scenarioId = this.state.selectedScenarioId;
        const routeId = this.state.selectedRoute ? this.state.selectedRoute.id : null;
        let calculateData = null;

        if (scenarioId && routeId) {
          showPlaceholder(`
            <div class="text-center text-muted py-4">
              <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
              <div class="mt-2">Расчёт трендов…</div>
            </div>
          `);
          let result;
          try {
            result = await this._loadRouteAnalysis({
              scenarioId,
              routeId,
              overrides: this._buildOverridesPayload(),
            });
          } catch (_e) {
            showPlaceholder(`
              <div class="mb-2">
                <i class="ti ti-alert-triangle" style="font-size: 2rem;"></i>
              </div>
              <div>Ошибка расчёта трендов (см. консоль).</div>
            `);
            return;
          }
          if (!result.ok) {
            showPlaceholder(`
              <div class="alert alert-danger" role="alert">
                ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
              </div>
            `);
            return;
          }
          calculateData = result.data;
        }

        const rowValuesByKey = (rowKey) => this._rowValuesByKey(calculateData, rowKey);

        const series = [
          { rowKey: "price_rub", name: "Цена тонны", color: "#1f6feb" },
          { rowKey: "cost", name: "Себестоимость", color: "#2da44e" },
          { rowKey: "rzd", name: "РЖД (итого), руб./т", color: "#8250df" },
          { rowKey: "operators", name: "Операторы, руб./т", color: "#d29922" },
          { rowKey: "transshipment", name: "Перевалка, руб./т", color: "#bc4c00" },
        ];

        const datasets = [];
        for (const s of series) {
          let dataPoints = rowValuesByKey(s.rowKey);
          if (!dataPoints) {
            const fallbackKeys = {
              price_rub: "market_price_per_ton",
              cost: "production_cost_per_ton",
              operators: "operators_cost_per_ton",
              transshipment: "transshipment_cost_per_ton",
              rzd: "rzd_cost_total_per_ton",
            };
            const routeKey = fallbackKeys[s.rowKey];
            const v = routeKey ? toNum(this.state.selectedRoute[routeKey]) : null;
            dataPoints = v != null ? years.map(() => v) : null;
          }
          if (!dataPoints || dataPoints.every((v) => v == null)) continue;
          datasets.push({
            label: s.name,
            data: dataPoints.map((v) => (v != null ? v : 0)),
            borderColor: s.color,
            backgroundColor: s.color,
            borderWidth: 3,
            pointRadius: 4,
            pointHoverRadius: 5,
            tension: 0,
          });
        }

        if (datasets.length === 0) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Для выбранного маршрута нет данных для построения трендов.</div>
          `);
          return;
        }

        showChart();

        this.state.trendsChart = new window.Chart(ctx, {
          type: "line",
          data: {
            labels: years,
            datasets,
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
              // Запас сверху, чтобы подписи в рамочке не упирались в край canvas.
              padding: { top: 24 },
            },
            plugins: {
              ...commonPlugins,
              title: {
                display: true,
                text: "Тренды по маршруту",
                align: "start",
                font: { size: 16, weight: "600" },
                padding: { bottom: 12 },
              },
              datalabels: {
                display: true,
                formatter: (value) => formatBox(value),
                anchor: "end",
                align: "top",
                offset: 8,
                backgroundColor: "#ffffff",
                borderColor: "#d0d7de",
                borderWidth: 1,
                borderRadius: 5,
                padding: { top: 2, bottom: 2, left: 6, right: 6 },
                color: "#111827",
                font: { size: 10, weight: "600" },
                clamp: true,
                clip: false,
              },
            },
            interaction: commonInteraction,
            scales: {
              x: {
                title: { display: true, text: "Год" },
                grid: { display: false },
                border: { display: false },
              },
              y: {
                grid: { display: false },
                border: { display: false },
                ticks: { display: false },
              },
            },
            elements: {
              line: { tension: 0 },
            },
          },
        });

        return;
      }

      if (typeValue === "structure") {
        const scenarioId = this.state.selectedScenarioId;
        const routeId = this.state.selectedRoute ? this.state.selectedRoute.id : null;
        let calculateData = this.state.activeCalculateData;

        if (scenarioId && routeId && !calculateData) {
          showPlaceholder(`
            <div class="text-center text-muted py-4">
              <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
              <div class="mt-2">Расчёт структуры…</div>
            </div>
          `);
          let result;
          try {
            result = await this._loadRouteAnalysis({
              scenarioId,
              routeId,
              overrides: this._buildOverridesPayload(),
            });
          } catch (_e) {
            showPlaceholder(`
              <div class="mb-2">
                <i class="ti ti-alert-triangle" style="font-size: 2rem;"></i>
              </div>
              <div>Ошибка расчёта структуры (см. консоль).</div>
            `);
            return;
          }
          if (!result.ok) {
            showPlaceholder(`
              <div class="alert alert-danger" role="alert">
                ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
              </div>
            `);
            return;
          }
          calculateData = result.data;
        }

        const yearParts = years.map((_y, index) =>
          this._structurePartsForYearIndex(calculateData, index),
        );
        if (yearParts.some((p) => !p)) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Для структуры нужна «Цена тонны» у маршрута.</div>
          `);
          return;
        }

        const partNames = yearParts[0].map((p) => p.name);
        const datasets = partNames.map((name, partIndex) => {
          const sample = yearParts[0][partIndex];
          return {
            label: name,
            data: yearParts.map((parts) => parts[partIndex].valuePct),
            borderColor: sample.color,
            backgroundColor: sample.color,
            borderWidth: 0,
            borderRadius: 4,
            barPercentage: 0.8,
            categoryPercentage: 0.8,
            stack: "stack",
          };
        });

        showChart();

        this.state.trendsChart = new window.Chart(ctx, {
          type: "bar",
          data: { labels: years, datasets },
          options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              ...commonPlugins,
              title: {
                display: true,
                text: "Структура по годам",
                align: "start",
                font: { size: 16, weight: "600" },
                padding: { bottom: 12 },
              },
              datalabels: {
                display: (ctx) => {
                  const v = ctx.dataset.data[ctx.dataIndex];
                  return v != null && Number(v) >= 6;
                },
                formatter: (value) => `${Number(value).toFixed(2)}%`,
                anchor: "center",
                align: "center",
                backgroundColor: "#ffffff",
                borderColor: "#d0d7de",
                borderWidth: 1,
                borderRadius: 5,
                padding: { top: 2, bottom: 2, left: 6, right: 6 },
                color: "#111827",
                font: { size: 10, weight: "600" },
                clamp: true,
              },
              tooltip: {
                enabled: true,
                callbacks: {
                  label: (ctx) => `${ctx.dataset.label}: ${Number(ctx.raw).toFixed(2)}%`,
                },
              },
            },
            interaction: {
              mode: "index",
              intersect: false,
              axis: "y",
            },
            scales: {
              x: {
                min: 0,
                max: 100,
                stacked: true,
                grid: { display: false },
                border: { display: false },
                ticks: {
                  callback: (v) => `${v}%`,
                },
              },
              y: {
                stacked: true,
                grid: { display: false },
                border: { display: false },
                title: { display: true, text: "Год" },
              },
            },
          },
        });

        return;
      }

      if (typeValue === "structure_aggregated" || typeValue === "structure_ts") {
        showPlaceholder(`
          <div class="text-center text-muted py-4">
            <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
            <div class="mt-2">Расчёт структуры…</div>
          </div>
        `);
        const result = await this._fetchRouteAnalysisData({});
        if (!result.ok) {
          showPlaceholder(`
            <div class="alert alert-danger" role="alert">
              ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
            </div>
          `);
          return;
        }
        const calculateData = result.data;
        const apiYears = Array.isArray(calculateData.years) ? calculateData.years : years;

        if (this.state.trendsChart) {
          try {
            this.state.trendsChart.destroy();
          } catch (_e) {
            // ignore
          }
          this.state.trendsChart = null;
        }

        if (typeValue === "structure_aggregated") {
          const gdfRows = apiYears.map((_year, index) => {
            const costsRub = this._rowRubByKey(calculateData, "cost", index);
            const transportRub = this._rowRubByKey(calculateData, "transport", index);
            const marginRub = this._rowRubByKey(calculateData, "marginality", index);
            const sum = costsRub + transportRub + marginRub;
            if (sum <= 0) {
              return {
                costs: 0,
                transport: 0,
                marginality: 0,
                costsRub: 0,
                transportRub: 0,
                marginRub: 0,
              };
            }
            return {
              costs: (costsRub / sum) * 100,
              transport: (transportRub / sum) * 100,
              marginality: (marginRub / sum) * 100,
              costsRub,
              transportRub,
              marginRub,
            };
          });
          const fakeRows = this._fakeGdfTr(gdfRows);
          const segmentDefs = [
            {
              key: "costs",
              label: "Себестоимость производства",
              color: "#4fb4ff",
              rubKey: "costsRub",
            },
            {
              key: "transport",
              label: "Транспортная составляющая",
              color: "#0091fe",
              rubKey: "transportRub",
            },
            {
              key: "marginality",
              label: "Маржинальность холдинга",
              color: "#003256",
              rubKey: "marginRub",
            },
          ];
          const datasets = segmentDefs.map((segment) => ({
            label: segment.label,
            data: fakeRows.map((row) => row[segment.key]),
            realPct: gdfRows.map((row) => row[segment.key]),
            rubValues: gdfRows.map((row) => row[segment.rubKey]),
            backgroundColor: segment.color,
            borderColor: segment.color,
            borderWidth: 0,
            stack: "stack",
          }));

          showChart();
          this.state.trendsChart = new window.Chart(ctx, {
            type: "bar",
            data: { labels: apiYears, datasets },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                ...commonPlugins,
                title: {
                  display: true,
                  text: "Структура укрупнённая",
                  align: "start",
                  font: { size: 16, weight: "600" },
                  padding: { bottom: 12 },
                },
                datalabels: {
                  display: (ctx) => {
                    const real = ctx.dataset.realPct[ctx.dataIndex];
                    return real != null && Number(real) >= 4;
                  },
                  formatter: (_value, ctx) => {
                    const real = ctx.dataset.realPct[ctx.dataIndex];
                    return `${Number(real).toFixed(1)}%`;
                  },
                  anchor: "center",
                  align: "center",
                  color: "#ffffff",
                  font: { size: 11, weight: "600" },
                },
                tooltip: {
                  enabled: true,
                  callbacks: {
                    label: (ctx) => {
                      const rub = ctx.dataset.rubValues[ctx.dataIndex];
                      const pct = ctx.dataset.realPct[ctx.dataIndex];
                      return `${ctx.dataset.label}: ${formatBox(rub)} руб. (${Number(pct).toFixed(1)}%)`;
                    },
                  },
                },
              },
              interaction: commonInteraction,
              scales: {
                x: { stacked: true, grid: { display: false } },
                y: {
                  stacked: true,
                  max: 100,
                  grid: { display: false },
                  ticks: { display: false },
                },
              },
            },
          });
          return;
        }

        const ts = calculateData.transport_structure;
        if (!ts) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Нет данных транспортной структуры.</div>
          `);
          return;
        }

        const rzdLoaded = this._mapYearValues(ts.rzd_loaded_by_year, apiYears);
        const rzdEmpty = this._mapYearValues(ts.rzd_empty_by_year, apiYears);
        const operators = apiYears.map((_y, index) =>
          this._rowRubByKey(calculateData, "operators", index),
        );
        const transshipment = apiYears.map((_y, index) =>
          this._rowRubByKey(calculateData, "transshipment", index),
        );

        const tsSegments = [
          {
            label: 'Расходы на оплату услуг ОАО "РЖД" (гружёный рейс)',
            data: rzdLoaded,
            color: "#0091fe",
            visible: true,
          },
        ];
        if (ts.show_empty_leg) {
          tsSegments.push({
            label: 'Расходы на оплату услуг ОАО "РЖД" (порожний рейс)',
            data: rzdEmpty,
            color: "#4fb4ff",
            visible: true,
          });
        }
        tsSegments.push(
          {
            label: "Расходы по оплате услуг операторов",
            data: operators,
            color: "#0072c8",
            visible: operators.some((v) => v > 0),
          },
          {
            label: "Расходы на перевалку",
            data: transshipment,
            color: "#005da2",
            visible: transshipment.some((v) => v > 0),
          },
        );

        const datasets = tsSegments
          .filter((segment) => segment.visible)
          .map((segment) => ({
            label: segment.label,
            data: segment.data,
            backgroundColor: segment.color,
            borderColor: segment.color,
            borderWidth: 0,
            stack: "stack",
          }));

        if (datasets.length === 0) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Нет данных для структуры ТС.</div>
          `);
          return;
        }

        showChart();
        this._renderTsAnnotations(apiYears, ts);
        this.state.trendsChart = new window.Chart(ctx, {
          type: "bar",
          data: { labels: apiYears, datasets },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              ...commonPlugins,
              title: {
                display: true,
                text: "Структура ТС",
                align: "start",
                font: { size: 16, weight: "600" },
                padding: { bottom: 12 },
              },
              datalabels: {
                display: (ctx) => {
                  const v = ctx.dataset.data[ctx.dataIndex];
                  return v != null && Number(v) > 0;
                },
                formatter: (value) => Number(value).toFixed(1),
                anchor: "center",
                align: "center",
                color: "#ffffff",
                font: { size: 10, weight: "600" },
              },
              tooltip: {
                enabled: true,
                callbacks: {
                  label: (ctx) =>
                    `${ctx.dataset.label}: ${formatBox(ctx.raw)} руб./т`,
                },
              },
            },
            interaction: commonInteraction,
            scales: {
              x: { stacked: true, grid: { display: false } },
              y: {
                stacked: true,
                grid: { display: false },
                ticks: {
                  callback: (v) => formatBox(v),
                },
              },
            },
          },
        });
      }
    }


    _setConfirmEnabled(enabled) {
      const btn = this._getConfirmButtonEl();
      if (!btn) return;
      // Важно: некоторые браузеры/шаблоны могут сохранять HTML-атрибут disabled,
      // поэтому снимаем его явно.
      btn.disabled = !enabled;
      if (enabled) {
        btn.removeAttribute("disabled");
      } else {
        btn.setAttribute("disabled", "disabled");
      }
    }

    _setLoading(loading) {
      const el = this._getLoadingEl();
      if (!el) return;
      setVisible(el, !!loading);
    }

    _showErrors(errors) {
      const el = this._getErrorsEl();
      if (!el) return;
      const list = (errors || []).filter(Boolean);
      if (list.length === 0) {
        el.classList.add("d-none");
        el.textContent = "";
        return;
      }
      el.classList.remove("d-none");
      el.textContent = list.join("\n");
    }

    _resetUi() {
      this._showErrors([]);
      this._setLoading(false);
      const emptyEl = this._getEmptyEl();
      if (emptyEl) setVisible(emptyEl, false);
      const listEl = this._getRouteListEl();
      if (listEl) listEl.innerHTML = "";
      this._setConfirmEnabled(false);
      this.state.pendingSelectedRoute = null;
    }

    _ensureModalHandlers() {
      const input = this._getSearchInputEl();
      if (input) {
        // Если Stimulus data-action не сработал (например, модалка перенесена в body),
        // подключаем обработчик вручную.
        input.removeEventListener("input", this.state.boundSearchHandler);
        input.addEventListener("input", this.state.boundSearchHandler);
      }

      const okBtn = this._getConfirmButtonEl();
      if (okBtn) {
        if (!this.state.boundConfirmHandler) {
          this.state.boundConfirmHandler = this.confirmSelection.bind(this);
        }
        okBtn.removeEventListener("click", this.state.boundConfirmHandler);
        okBtn.addEventListener("click", this.state.boundConfirmHandler);
      }
    }

    _getModalEl() {
      return (
        this.state.modalEl || document.getElementById("routeAnalysisRouteModal")
      );
    }

    _getSearchInputEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector("#routeAnalysisRouteSearchInput") : null;
    }

    _getRouteListEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="routeList"]') : null;
    }

    _getLoadingEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="loading"]') : null;
    }

    _getEmptyEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="empty"]') : null;
    }

    _getErrorsEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="errors"]') : null;
    }

    _getConfirmButtonEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="confirmButton"]') : null;
    }

    _updateEqualizerVisibility(show) {
      if (this.hasEqualizerEmptyTarget) {
        setVisible(this.equalizerEmptyTarget, !show);
      }
      if (this.hasEqualizerControlsTarget) {
        setVisible(this.equalizerControlsTarget, show);
      }
    }

    _resetEqualizer() {
      this.state.equalizerBaseline = null;
      this.state.equalizerOverrides = {};
      clearTimeout(this.state.equalizerDebounceTimer);
      this._updateEqualizerVisibility(false);
      if (this.hasEqualizerPanelTarget) {
        this.equalizerPanelTarget.innerHTML = "";
      }
      if (this.hasEqualizerTypeSelectTarget) {
        this.equalizerTypeSelectTarget.innerHTML = "";
      }
    }

    _getVisibleEqualizerTypes() {
      const baseline = this.state.equalizerBaseline;
      if (!baseline || !Array.isArray(baseline.types)) return [];
      return baseline.types.filter((item) => item.visible !== false);
    }

    _getEqualizerTypeDef(typeKey) {
      const types = this._getVisibleEqualizerTypes();
      return types.find((item) => item.key === typeKey) || null;
    }

    _getEqualizerValue(typeKey, year) {
      const yearKey = String(year);
      const overrides = this.state.equalizerOverrides[typeKey];
      if (overrides && overrides[year] != null) {
        return Number(overrides[year]);
      }
      const typeDef = this._getEqualizerTypeDef(typeKey);
      if (!typeDef || !typeDef.values) return 0;
      const raw = typeDef.values[yearKey];
      const n = Number(String(raw).replace(",", "."));
      return Number.isFinite(n) ? n : 0;
    }

    _buildOverridesPayload() {
      const payload = {};
      for (const [typeKey, yearMap] of Object.entries(this.state.equalizerOverrides)) {
        if (!yearMap || typeof yearMap !== "object") continue;
        const out = {};
        for (const [year, value] of Object.entries(yearMap)) {
          if (value == null || Number.isNaN(Number(value))) continue;
          out[String(year)] = value;
        }
        if (Object.keys(out).length > 0) {
          payload[typeKey] = out;
        }
      }
      return Object.keys(payload).length > 0 ? payload : null;
    }

    _buildEqualizerTypeOptions() {
      if (!this.hasEqualizerTypeSelectTarget) return;
      const types = this._getVisibleEqualizerTypes();
      this.equalizerTypeSelectTarget.innerHTML = "";
      for (const typeDef of types) {
        const opt = document.createElement("option");
        opt.value = typeDef.key;
        opt.textContent = typeDef.label || typeDef.key;
        this.equalizerTypeSelectTarget.appendChild(opt);
      }
    }

    _renderEqualizerPanel() {
      if (!this.hasEqualizerPanelTarget) return;
      const scenario = this.state.selectedScenario;
      const startYear = scenario && scenario.start_year ? Number(scenario.start_year) : null;
      const endYear = scenario && scenario.end_year ? Number(scenario.end_year) : null;
      if (!startYear || !endYear) {
        this.equalizerPanelTarget.innerHTML = "";
        return;
      }

      const typeKey = this.hasEqualizerTypeSelectTarget
        ? this.equalizerTypeSelectTarget.value
        : null;
      const typeDef = typeKey ? this._getEqualizerTypeDef(typeKey) : null;
      if (!typeDef) {
        this.equalizerPanelTarget.innerHTML = "";
        return;
      }

      if (this.hasEqualizerUnitHintTarget) {
        this.equalizerUnitHintTarget.textContent = typeDef.unit
          ? `Единица: ${typeDef.unit}`
          : "";
      }

      const step = Number(typeDef.step) || 1;
      const years = [];
      for (let y = startYear; y <= endYear; y += 1) years.push(y);

      const cols = years
        .map((year) => {
          const value = this._getEqualizerValue(typeKey, year);
          const max = value === 0 ? 1000 : value * 2;
          const min = 0;
          return `
            <div class="route-analysis-equalizer__year-col" data-year="${year}">
              <div class="route-analysis-equalizer__year-label">${escapeHtml(String(year))}</div>
              <input
                type="number"
                class="form-control form-control-sm route-analysis-equalizer__value-input"
                data-equalizer-input
                data-equalizer-type="${escapeHtml(typeKey)}"
                data-equalizer-year="${year}"
                value="${escapeHtml(String(value))}"
                step="${escapeHtml(String(step))}"
                min="${min}"
              />
              <div class="route-analysis-equalizer__slider-wrap">
                <input
                  type="range"
                  class="route-analysis-equalizer__slider"
                  data-equalizer-slider
                  data-equalizer-type="${escapeHtml(typeKey)}"
                  data-equalizer-year="${year}"
                  min="${min}"
                  max="${max}"
                  step="${escapeHtml(String(step))}"
                  value="${escapeHtml(String(value))}"
                />
              </div>
            </div>
          `;
        })
        .join("");

      this.equalizerPanelTarget.innerHTML = cols;

      const onInput = (event) => {
        const el = event.target;
        const t = el.getAttribute("data-equalizer-type");
        const y = Number(el.getAttribute("data-equalizer-year"));
        if (!t || Number.isNaN(y)) return;
        const num = Number(String(el.value).replace(",", "."));
        if (!Number.isFinite(num)) return;
        this._onEqualizerValueChange(t, y, num, el);
      };

      this.equalizerPanelTarget
        .querySelectorAll("[data-equalizer-input], [data-equalizer-slider]")
        .forEach((el) => {
          el.addEventListener("input", onInput);
        });
    }

    _onEqualizerValueChange(typeKey, year, value, sourceEl) {
      const col = sourceEl.closest("[data-year]");
      if (col) {
        const input = col.querySelector("[data-equalizer-input]");
        const slider = col.querySelector("[data-equalizer-slider]");
        if (input && input !== sourceEl) input.value = String(value);
        if (slider && slider !== sourceEl) {
          const max = value === 0 ? 1000 : value * 2;
          slider.max = String(max);
          slider.value = String(value);
        }
      }

      if (!this.state.equalizerOverrides[typeKey]) {
        this.state.equalizerOverrides[typeKey] = {};
      }
      this.state.equalizerOverrides[typeKey][year] = value;
      this._scheduleEqualizerRecalc();
    }

    _scheduleEqualizerRecalc() {
      clearTimeout(this.state.equalizerDebounceTimer);
      this.state.equalizerDebounceTimer = setTimeout(() => {
        this._recalculateWithOverrides();
      }, 250);
    }

    async _loadEqualizerBaseline() {
      if (!this.state.selectedRoute || !this.state.selectedScenarioId) {
        this._resetEqualizer();
        return;
      }

      const result = await this._loadRouteAnalysis({
        scenarioId: this.state.selectedScenarioId,
        routeId: this.state.selectedRoute.id,
      });
      if (!result.ok) {
        this._resetEqualizer();
        return;
      }

      this.state.equalizerBaseline = result.data.equalizer || null;
      this._buildEqualizerTypeOptions();
      this._updateEqualizerVisibility(true);
      this._renderEqualizerPanel();
    }

    async _recalculateWithOverrides() {
      if (!this.state.selectedRoute || !this.state.selectedScenarioId) return;
      if (this.state.equalizerRecalcInFlight) return;

      const overrides = this._buildOverridesPayload();
      if (!overrides) return;

      this.state.equalizerRecalcInFlight = true;
      try {
        const result = await this._loadRouteAnalysis({
          scenarioId: this.state.selectedScenarioId,
          routeId: this.state.selectedRoute.id,
          overrides,
          useCache: false,
        });
        if (result.ok) {
          await this._renderDiagram();
        }
      } finally {
        this.state.equalizerRecalcInFlight = false;
      }
    }

    async _loadRouteAnalysis({ scenarioId, routeId, overrides, useCache = true }) {
      if (!this.routeAnalysisUrlValue) {
        return { ok: false, errors: ["URL route_analysis не задан"] };
      }

      const overridesKey = overrides ? JSON.stringify(overrides) : "";
      const cacheKey = `${scenarioId}:${routeId}:${overridesKey}`;
      if (useCache && this.state.routeAnalysisCache.has(cacheKey)) {
        const cached = this.state.routeAnalysisCache.get(cacheKey);
        this.state.activeCalculateData = cached;
        return { ok: true, data: cached };
      }

      const body = {
        scenario_id: Number(scenarioId),
        route_id: Number(routeId),
      };
      if (overrides) {
        body.overrides = overrides;
      }

      const { data } = await fetchJson(this.routeAnalysisUrlValue, {
        method: "POST",
        body: JSON.stringify(body),
      });

      if (!data || !data.success) {
        return {
          ok: false,
          errors: (data && data.errors) || ["Ошибка расчёта структуры маршрута"],
        };
      }

      this.state.routeAnalysisCache.set(cacheKey, data);
      this.state.activeCalculateData = data;
      if (!overrides && data.equalizer) {
        this.state.equalizerBaseline = data.equalizer;
      }
      return { ok: true, data };
    }

    _rowValuesByKey(calculateData, rowKey) {
      if (!calculateData || !Array.isArray(calculateData.rows)) return null;
      const row = calculateData.rows.find((item) => item.key === rowKey);
      if (!row || !Array.isArray(row.values)) return null;
      return row.values.map((value) => {
        if (value != null && typeof value === "object" && value.rub != null) {
          return Number(String(value.rub).replace(",", "."));
        }
        return Number(String(value).replace(",", "."));
      });
    }

    _structurePartsForYearIndex(calculateData, yearIndex) {
      const toNum = (val) => {
        if (val == null) return null;
        const n = Number(String(val).replace(",", "."));
        return Number.isFinite(n) ? n : null;
      };

      const rowValuesByKey = (rowKey) => {
        if (!calculateData || !Array.isArray(calculateData.rows)) return null;
        const row = calculateData.rows.find((item) => item.key === rowKey);
        if (!row || !Array.isArray(row.values)) return null;
        const value = row.values[yearIndex];
        if (value != null && typeof value === "object" && value.rub != null) {
          return toNum(value.rub);
        }
        return toNum(value);
      };

      const price = rowValuesByKey("price_rub");
      const production = rowValuesByKey("cost");
      const rzd = rowValuesByKey("rzd");
      const ops = rowValuesByKey("operators");
      const trans = rowValuesByKey("transshipment");

      const base = price && price > 0 ? price : null;
      if (!base) return null;

      const clamp0 = (v) => (Number.isFinite(v) ? Math.max(v, 0) : 0);
      const round2 = (v) => Number(v.toFixed(2));
      const percentRaw = (v) => (v != null ? (v / base) * 100 : 0);

      const parts = [
        {
          name: "Себестоимость производства",
          valuePct: clamp0(percentRaw(production)),
          color: "#2da44e",
        },
        {
          name: 'Расходы ОАО "РЖД"',
          valuePct: clamp0(percentRaw(rzd)),
          color: "#8250df",
        },
        {
          name: "Расходы операторов",
          valuePct: clamp0(percentRaw(ops)),
          color: "#d29922",
        },
        {
          name: "Расходы на перевалку",
          valuePct: clamp0(percentRaw(trans)),
          color: "#bc4c00",
        },
      ];

      const sumKnown = [production, rzd, ops, trans].reduce(
        (acc, v) => (v != null ? acc + v : acc),
        0,
      );
      const marginPctRaw = ((base - sumKnown) / base) * 100;
      const marginPctNonNeg = clamp0(marginPctRaw);
      const usedRaw = parts.reduce((acc, p) => acc + p.valuePct, 0);
      const totalRaw = usedRaw + marginPctNonNeg;
      if (!totalRaw) return null;

      const scale = 100 / totalRaw;
      for (const p of parts) {
        p.valuePct = round2(p.valuePct * scale);
      }

      const marginPart = {
        name: "Маржинальность холдинга",
        valuePct: round2(marginPctNonNeg * scale),
        color: "#cf222e",
      };
      const usedRounded = parts.reduce((acc, p) => acc + p.valuePct, 0);
      marginPart.valuePct = round2(100 - usedRounded);
      if (marginPart.valuePct < 0) marginPart.valuePct = 0;
      parts.push(marginPart);
      return parts;
    }

    _formatMoney(val) {
      const n = Number(String(val).replace(",", "."));
      if (!Number.isFinite(n)) return "—";
      return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(
        Math.round(n),
      );
    }

    _formatPct(val) {
      const n = Number(String(val).replace(",", "."));
      if (!Number.isFinite(n)) return "0.00";
      return n.toFixed(2);
    }

    _hideDiagramExtras() {
      const tsEl = document.getElementById("routeAnalysisTsAnnotations");
      if (tsEl) {
        tsEl.style.display = "none";
        tsEl.innerHTML = "";
      }
      const effectsEl = document.getElementById("routeAnalysisEffectsTableWrap");
      if (effectsEl) {
        effectsEl.style.display = "none";
        effectsEl.innerHTML = "";
      }
      const kpiEl = document.getElementById("routeAnalysisKpiWrap");
      if (kpiEl) {
        kpiEl.style.display = "none";
        kpiEl.innerHTML = "";
      }
    }

    _fakeGdfTr(yearRows) {
      const partCh = 0.2;
      return yearRows.map((row) => {
        const next = { ...row };
        const tail = next.costs * partCh;
        const keys = ["transport", "marginality"];
        const nonZero = keys.filter((key) => next[key] !== 0);
        if (nonZero.length > 0) {
          const add = Math.round((tail / nonZero.length) * 100) / 100;
          for (const key of keys) {
            if (next[key] !== 0) next[key] += add;
          }
        }
        next.costs *= 1 - partCh;
        return next;
      });
    }

    _rowRubByKey(calculateData, rowKey, yearIndex) {
      if (!calculateData || !Array.isArray(calculateData.rows)) return 0;
      const row = calculateData.rows.find((item) => item.key === rowKey);
      if (!row || !Array.isArray(row.values)) return 0;
      const value = row.values[yearIndex];
      if (value != null && typeof value === "object" && value.rub != null) {
        const n = Number(String(value.rub).replace(",", "."));
        return Number.isFinite(n) ? n : 0;
      }
      const n = Number(String(value).replace(",", "."));
      return Number.isFinite(n) ? n : 0;
    }

    _mapYearValues(mapByYear, years) {
      if (!mapByYear) return years.map(() => 0);
      return years.map((year) => {
        const raw = mapByYear[String(year)];
        const n = Number(String(raw).replace(",", "."));
        return Number.isFinite(n) ? n : 0;
      });
    }

    async _fetchRouteAnalysisData({ loadingMessage }) {
      const scenarioId = this.state.selectedScenarioId;
      const routeId = this.state.selectedRoute ? this.state.selectedRoute.id : null;
      if (!scenarioId || !routeId) {
        return { ok: false, errors: ["Не удалось определить сценарий и маршрут"] };
      }
      try {
        const result = await this._loadRouteAnalysis({
          scenarioId,
          routeId,
          overrides: this._buildOverridesPayload(),
        });
        return result;
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("[route-analysis] route_analysis failed", e);
        return { ok: false, errors: ["Ошибка расчёта (см. консоль)"] };
      }
    }

    _renderTsAnnotations(years, transportStructure) {
      const el = document.getElementById("routeAnalysisTsAnnotations");
      if (!el || !transportStructure) return;
      const transportPct = transportStructure.transport_pct_by_year || {};
      const marginPct = transportStructure.marginality_pct_by_year || {};
      el.innerHTML = years
        .map((year) => {
          const transport = transportPct[String(year)] ?? "0";
          const margin = marginPct[String(year)] ?? "0";
          return `
            <div class="route-analysis-ts-annotations__year">
              <div class="route-analysis-ts-annotations__year-label">${escapeHtml(String(year))}</div>
              <span class="route-analysis-ts-annotations__badge route-analysis-ts-annotations__badge--transport">
                ${escapeHtml(transport)}%
              </span>
              <span class="route-analysis-ts-annotations__badge route-analysis-ts-annotations__badge--margin">
                ${escapeHtml(margin)}%
              </span>
            </div>
          `;
        })
        .join("");
      el.style.display = years.length ? "" : "none";
    }

    _renderEffectsTable(containerEl, data) {
      if (!containerEl) return;
      const years = Array.isArray(data.years) ? data.years : [];
      const rows = data.effects && Array.isArray(data.effects.rows) ? data.effects.rows : [];
      if (!years.length || !rows.length) {
        containerEl.innerHTML = `
          <div class="text-center text-muted py-4">Нет данных для таблицы эффектов.</div>
        `;
        return;
      }

      const thYears = years
        .map((y) => `<th class="text-end">${escapeHtml(String(y))}</th>`)
        .join("");

      const renderCell = (cell) => {
        if (!cell) return `<td class="text-end">—</td>`;
        const rub = cell.rub != null ? cell.rub : "0";
        const pctNum = Number(String(cell.pct).replace(",", "."));
        const pctStr = this._formatPct(cell.pct);
        const pctClass =
          Number.isFinite(pctNum) && pctNum < 0 ? "text-danger" : "";
        const pctPrefix = Number.isFinite(pctNum) && pctNum > 0 ? "+" : "";
        return `
          <td class="text-end ${pctClass}">
            ${escapeHtml(rub)}<br />
            <span class="${pctClass}">(${escapeHtml(pctPrefix + pctStr)}%)</span>
          </td>
        `;
      };

      const tbody = rows
        .map((row) => {
          const values = row.values || {};
          const cells = years.map((y) => renderCell(values[String(y)])).join("");
          return `
            <tr>
              <td class="text-muted">${escapeHtml(row.label || row.key || "")}</td>
              ${cells}
            </tr>
          `;
        })
        .join("");

      containerEl.innerHTML = `
        <div class="table-responsive">
          <table class="table table-sm table-vcenter">
            <thead>
              <tr>
                <th>Показатель</th>
                ${thYears}
              </tr>
            </thead>
            <tbody>${tbody}</tbody>
          </table>
        </div>
      `;
    }

    _renderKpiMetric(metric) {
      if (!metric) return "";
      const rub =
        metric.rub != null && metric.rub !== ""
          ? `${this._formatMoney(metric.rub)} руб.`
          : "—";
      const pct =
        metric.pct != null && metric.pct !== ""
          ? `${this._formatPct(metric.pct)}%`
          : "—";
      return `
        <div class="route-analysis-kpi-metric">
          <div class="route-analysis-kpi-metric__row">
            <span class="route-analysis-kpi-metric__pct">${escapeHtml(pct)}</span>
            <span class="route-analysis-kpi-metric__rub">${escapeHtml(rub)}</span>
          </div>
          <div class="route-analysis-kpi-metric__label">${escapeHtml(metric.label || "")}</div>
        </div>
      `;
    }

    _renderKpiCards(containerEl, data) {
      if (!containerEl) return;
      const items = data.kpi && Array.isArray(data.kpi.by_year) ? data.kpi.by_year : [];
      if (!items.length) {
        containerEl.innerHTML = `
          <div class="text-center text-muted py-4 w-100">Нет KPI для отображения.</div>
        `;
        return;
      }

      containerEl.innerHTML = items
        .map((item) => {
          const metrics = [
            item.transport,
            item.rzd,
            item.marginality,
            item.volume_share,
            item.elasticity,
          ]
            .filter(Boolean)
            .map((metric) => this._renderKpiMetric(metric))
            .join("");
          return `
            <div class="route-analysis-kpi-card">
              <div class="route-analysis-kpi-card__title">${escapeHtml(String(item.year))} год</div>
              ${metrics}
            </div>
          `;
        })
        .join("");
    }

    async _renderStructureTable({ scenarioId, routeId, containerEl }) {
      if (!containerEl) return;

      containerEl.innerHTML = `
        <div class="text-center text-muted py-4">
          <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
          <div class="mt-2">Расчёт таблицы…</div>
        </div>
      `;

      let result;
      try {
        result = await this._loadRouteAnalysis({
          scenarioId,
          routeId,
          overrides: this._buildOverridesPayload(),
        });
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("[route-analysis] route_analysis failed", e);
        containerEl.innerHTML = `
          <div class="alert alert-danger" role="alert">
            Ошибка расчёта таблицы (см. консоль).
          </div>
        `;
        return;
      }

      if (!result.ok) {
        containerEl.innerHTML = `
          <div class="alert alert-danger" role="alert">
            ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
          </div>
        `;
        return;
      }

      const data = result.data;
      const years = Array.isArray(data.years) ? data.years : [];
      const rows = Array.isArray(data.rows) ? data.rows : [];

      if (years.length === 0 || rows.length === 0) {
        containerEl.innerHTML = `
          <div class="text-center text-muted py-4">
            Нет данных для отображения таблицы.
          </div>
        `;
        return;
      }

      const thYears = years
        .map((y) => `<th class="text-end">${escapeHtml(String(y))}</th>`)
        .join("");

      const renderCell = (row, value) => {
        if (row.format === "marginality") {
          const rubRaw = value && value.rub != null ? value.rub : 0;
          const pctRaw = value && value.pct != null ? value.pct : 0;
          const rub = Number(String(rubRaw).replace(",", "."));
          const cls =
            Number.isFinite(rub) && rub < 0
              ? "text-danger"
              : Number.isFinite(rub) && rub > 0
                ? "text-success"
                : "";
          const rubStr = this._formatMoney(rubRaw);
          const pctStr = this._formatPct(pctRaw);
          return `<td class="text-end ${cls}">${escapeHtml(rubStr)} (${escapeHtml(pctStr)}%)</td>`;
        }

        const money = this._formatMoney(value);
        return `<td class="text-end">${escapeHtml(money)}</td>`;
      };

      const tbody = rows
        .map((row) => {
          const values = Array.isArray(row.values) ? row.values : [];
          const cells = years
            .map((_y, idx) => renderCell(row, values[idx]))
            .join("");
          return `
            <tr>
              <td class="text-muted">${escapeHtml(row.label || row.key || "")}</td>
              ${cells}
            </tr>
          `;
        })
        .join("");

      containerEl.innerHTML = `
        <div class="table-responsive">
          <table class="table table-sm table-vcenter">
            <thead>
              <tr>
                <th>Параметр</th>
                ${thYears}
              </tr>
            </thead>
            <tbody>
              ${tbody}
            </tbody>
          </table>
        </div>
      `;
    }
  }

  application.register(
    "route-analysis-route-picker",
    RouteAnalysisRoutePickerController,
  );
})();

