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
    ];

    static values = {
      scenariosUrl: String,
      routesUrl: String,
      calculateRouteUrl: String,
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
        calculateRouteCache: new Map(),
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
      this._setScenario(scenarioId);
      this._resetRouteSearch();
      this._renderRouteDetails(null);
      this.state.selectedRoute = null;
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

    confirmSelection() {
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

      this._renderDiagram();
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
      const placeholderEl =
        this.hasDiagramPlaceholderTarget
          ? this.diagramPlaceholderTarget
          : document.getElementById("routeAnalysisDiagramPlaceholder");

      const typeSelect =
        this.hasDiagramTypeSelectTarget ? this.diagramTypeSelectTarget : null;
      const typeValue = typeSelect ? typeSelect.value : "trends";

      const labels = {
        trends: "Тренды",
        structure: "Структура",
        structure_table: "Структура (табл.)",
        structure_aggregated: "Структура укрупненная",
        structure_ts: "Структура ТС",
      };
      const label = labels[typeValue] || "Диаграмма";

      const showPlaceholder = (html) => {
        if (chartWrapEl) {
          chartWrapEl.style.display = "none";
        }
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
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
        if (placeholderEl) placeholderEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (chartWrapEl) chartWrapEl.style.display = "";
      };

      const showTable = () => {
        if (placeholderEl) placeholderEl.style.display = "none";
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (tableWrapEl) tableWrapEl.style.display = "";
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
        const series = [
          { key: "market_price_per_ton", name: "Цена тонны", color: "#1f6feb" },
          { key: "total_cost_per_ton", name: "Себестоимость", color: "#2da44e" },
          { key: "rzd_cost_total_per_ton", name: "РЖД (итого), руб./т", color: "#8250df" },
          { key: "operators_cost_per_ton", name: "Операторы, руб./т", color: "#d29922" },
          { key: "transshipment_cost_per_ton", name: "Перевалка, руб./т", color: "#bc4c00" },
        ];

        const datasets = [];
        for (const s of series) {
          const v = toNum(this.state.selectedRoute[s.key]);
          if (v == null) continue;
          datasets.push({
            label: s.name,
            data: years.map(() => v),
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
        const price = toNum(this.state.selectedRoute.market_price_per_ton);
        const totalCost = toNum(this.state.selectedRoute.total_cost_per_ton);
        const production = toNum(this.state.selectedRoute.production_cost_per_ton);
        const rzd = toNum(this.state.selectedRoute.rzd_cost_total_per_ton);
        const ops = toNum(this.state.selectedRoute.operators_cost_per_ton);
        const trans = toNum(this.state.selectedRoute.transshipment_cost_per_ton);

        const base = price && price > 0 ? price : null;
        if (!base) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Для структуры нужна «Цена тонны» у маршрута.</div>
          `);
          return;
        }

        const sumKnown = [production, rzd, ops, trans].reduce(
          (acc, v) => (v != null ? acc + v : acc),
          0,
        );
        const costForMargin = totalCost != null ? totalCost : sumKnown;

        // Считаем проценты от цены. Если суммарно > 100% (затраты > цены),
        // нормализуем сегменты, чтобы сумма всегда была ровно 100%.
        const percentRaw = (v) => (v != null ? (v / base) * 100 : 0);
        const clamp0 = (v) => (Number.isFinite(v) ? Math.max(v, 0) : 0);
        const round2 = (v) => Number(v.toFixed(2));

        const parts = [
          { name: "Себестоимость производства", valuePct: clamp0(percentRaw(production)), color: "#2da44e" },
          { name: "Расходы ОАО \"РЖД\"", valuePct: clamp0(percentRaw(rzd)), color: "#8250df" },
          { name: "Расходы операторов", valuePct: clamp0(percentRaw(ops)), color: "#d29922" },
          { name: "Расходы на перевалку", valuePct: clamp0(percentRaw(trans)), color: "#bc4c00" },
        ];

        const marginPctRaw = ((base - costForMargin) / base) * 100;
        const marginPctNonNeg = clamp0(marginPctRaw);

        const usedRaw = parts.reduce((acc, p) => acc + p.valuePct, 0);
        const totalRaw = usedRaw + marginPctNonNeg;

        // Если totalRaw == 0 (все нули) — рисовать нечего.
        if (!totalRaw) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Для структуры не хватает данных по компонентам затрат.</div>
          `);
          return;
        }

        const scale = 100 / totalRaw;
        for (const p of parts) {
          p.valuePct = round2(p.valuePct * scale);
        }

        const marginPart = {
          name: "Маржинальность холдинга",
          valuePct: round2(marginPctNonNeg * scale),
          color: "#cf222e",
        };

        // Финальная подгонка из-за округления: скорректируем маржу, чтобы сумма = 100.00
        const usedRounded = parts.reduce((acc, p) => acc + p.valuePct, 0);
        marginPart.valuePct = round2(100 - usedRounded);
        if (marginPart.valuePct < 0) marginPart.valuePct = 0;

        parts.push(marginPart);

        const datasets = parts.map((p) => ({
          label: p.name,
          data: years.map(() => p.valuePct),
          borderColor: p.color,
          backgroundColor: p.color,
          borderWidth: 0,
          borderRadius: 4,
          barPercentage: 0.8,
          categoryPercentage: 0.8,
          stack: "stack",
        }));

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

      // Остальные типы пока заглушка.
      const routeCode = (this.state.selectedRoute.route_code || "").trim();
      showPlaceholder(`
        <div class="mb-2">
          <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
        </div>
        <div>${escapeHtml(label)}: заглушка для маршрута ${escapeHtml(routeCode || "—")}</div>
      `);
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

    async _loadCalculateRoute({ scenarioId, routeId }) {
      if (!this.calculateRouteUrlValue) {
        return { ok: false, errors: ["URL calculate_route не задан"] };
      }

      const cacheKey = `${scenarioId}:${routeId}`;
      if (this.state.calculateRouteCache.has(cacheKey)) {
        return { ok: true, data: this.state.calculateRouteCache.get(cacheKey) };
      }

      const { data } = await fetchJson(this.calculateRouteUrlValue, {
        method: "POST",
        body: JSON.stringify({
          scenario_id: Number(scenarioId),
          route_id: Number(routeId),
        }),
      });

      if (!data || !data.success) {
        return {
          ok: false,
          errors: (data && data.errors) || ["Ошибка расчёта структуры маршрута"],
        };
      }

      this.state.calculateRouteCache.set(cacheKey, data);
      return { ok: true, data };
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
        result = await this._loadCalculateRoute({ scenarioId, routeId });
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("[route-analysis] calculate_route failed", e);
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

