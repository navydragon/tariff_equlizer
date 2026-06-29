import { fetchJson } from "../lib/http.js";
import { escapeHtml } from "../lib/dom.js";
import {
  ROUTE_ANALYTICS_METRICS,
  createAnalyticsBarChart,
  destroyAnalyticsChart,
  renderAnalyticsTable,
  renderLoadingTable,
} from "../lib/route_analytics_presentation.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus is not available for route-analytics.");
    return;
  }

  const METRICS = ROUTE_ANALYTICS_METRICS;

  class RouteAnalyticsController extends Stimulus.Controller {
    static targets = [
      "routeSetSelect",
      "dimensionSelect",
      "tabPanel",
      "tableWrap",
      "chartCanvas",
    ];

    static values = {
      routeSetListUrl: String,
      aggregateUrl: String,
      debounceMs: { type: Number, default: 300 },
    };

    connect() {
      this.state = {
        routeSetId: null,
        dimension: this.hasDimensionSelectTarget
          ? this.dimensionSelectTarget.value
          : "cargo_group",
        loadedTabs: new Set(),
        charts: {},
        filterTimer: null,
        activeMetric: "count",
        filterGeneration: 0,
      };

      this._loadRouteSets();
    }

    disconnect() {
      if (this.state?.filterTimer) {
        clearTimeout(this.state.filterTimer);
      }
      this._destroyAllCharts();
    }

    onFilterChange() {
      this.state.routeSetId = this._readRouteSetId();
      this.state.dimension = this.hasDimensionSelectTarget
        ? this.dimensionSelectTarget.value
        : "cargo_group";

      this.state.filterGeneration += 1;
      this.state.loadedTabs.clear();
      this._destroyAllCharts();
      this._resetAllPanes();

      if (this.state.filterTimer) {
        clearTimeout(this.state.filterTimer);
      }

      this.state.filterTimer = setTimeout(() => {
        this.state.filterTimer = null;
        if (this.state.activeMetric && this._filtersReady()) {
          this._loadMetric(this.state.activeMetric);
        }
      }, this.debounceMsValue);
    }

    onTabShown(event) {
      const metric = event.target?.dataset?.routeAnalyticsMetricParam;
      if (!metric || !METRICS.includes(metric)) {
        return;
      }

      this.state.activeMetric = metric;
      if (!this._filtersReady()) {
        return;
      }

      if (this.state.loadedTabs.has(metric)) {
        return;
      }

      this._loadMetric(metric);
    }

    async _loadRouteSets() {
      if (!this.hasRouteSetSelectTarget) return;

      const select = this.routeSetSelectTarget;
      select.innerHTML = '<option value="">Загрузка...</option>';

      const url = `${this.routeSetListUrlValue}?page=1&page_size=1000`;
      const { data } = await fetchJson(url, { method: "GET" });
      if (!data || !data.success) {
        select.innerHTML = '<option value="">Ошибка загрузки</option>';
        return;
      }

      const items = data.items || [];
      if (!items.length) {
        select.innerHTML = '<option value="">Нет наборов</option>';
        return;
      }

      const sorted = [...items].sort(
        (a, b) => (a.routes_count || 0) - (b.routes_count || 0),
      );

      const options = [
        '<option value="">— выберите набор —</option>',
        ...sorted.map((item) => {
          const count =
            item.routes_count != null
              ? ` (${Number(item.routes_count).toLocaleString("ru-RU")} маршр.)`
              : "";
          return `<option value="${item.id}">${escapeHtml(item.code || "")} — ${escapeHtml(
            item.name || "",
          )}${count}</option>`;
        }),
      ];
      select.innerHTML = options.join("");
    }

    _readRouteSetId() {
      if (!this.hasRouteSetSelectTarget) return null;
      const raw = this.routeSetSelectTarget.value;
      const parsed = raw ? parseInt(raw, 10) : null;
      return parsed && !Number.isNaN(parsed) ? parsed : null;
    }

    _filtersReady() {
      return Boolean(this.state.routeSetId && this.state.dimension);
    }

    _resetAllPanes() {
      METRICS.forEach((metric) => {
        const panel = this._findPanel(metric);
        if (!panel) return;

        const placeholder = panel.querySelector(".route-analytics-pane-placeholder");
        const content = panel.querySelector(".route-analytics-pane-content");
        if (placeholder) {
          placeholder.classList.remove("d-none");
          placeholder.textContent =
            "Выберите набор маршрутов и параметр группировки.";
        }
        if (content) {
          content.classList.add("d-none");
        }

        const tableWrap = this._findTableWrap(metric);
        if (tableWrap) {
          tableWrap.innerHTML = "";
          tableWrap.classList.remove("route-analytics-table-wrap--loading");
        }
      });
    }

    async _loadMetric(metric) {
      if (!this._filtersReady()) {
        return;
      }

      const generation = this.state.filterGeneration;
      const panel = this._findPanel(metric);
      const tableWrap = this._findTableWrap(metric);
      const chartCanvas = this._findChartCanvas(metric);
      if (!panel || !tableWrap || !chartCanvas) {
        return;
      }

      const placeholder = panel.querySelector(".route-analytics-pane-placeholder");
      const content = panel.querySelector(".route-analytics-pane-content");
      if (placeholder) placeholder.classList.add("d-none");
      if (content) content.classList.remove("d-none");

      renderLoadingTable(tableWrap);

      const params = new URLSearchParams();
      params.set("route_set_id", String(this.state.routeSetId));
      params.set("dimension", this.state.dimension);
      params.set("metric", metric);

      try {
        const { data } = await fetchJson(
          `${this.aggregateUrlValue}?${params.toString()}`,
          { method: "GET" },
        );

        if (generation !== this.state.filterGeneration) {
          return;
        }

        if (!data || !data.success) {
          const errors = (data && data.errors) || ["Ошибка загрузки данных"];
          tableWrap.classList.remove("route-analytics-table-wrap--loading");
          tableWrap.innerHTML = `<div class="text-danger py-4 text-center">${escapeHtml(
            errors.join(", "),
          )}</div>`;
          return;
        }

        this.state.loadedTabs.add(metric);
        renderAnalyticsTable(tableWrap, data);
        this._destroyChart(metric);
        this.state.charts[metric] = createAnalyticsBarChart(chartCanvas, data);
      } catch (error) {
        if (generation !== this.state.filterGeneration) {
          return;
        }
        console.error("[route-analytics] aggregate failed", error);
        tableWrap.classList.remove("route-analytics-table-wrap--loading");
        tableWrap.innerHTML =
          '<div class="text-danger py-4 text-center">Не удалось загрузить данные.</div>';
      }
    }

    _findPanel(metric) {
      return this.tabPanelTargets.find(
        (panel) => panel.dataset.metric === metric,
      );
    }

    _findTableWrap(metric) {
      return this.tableWrapTargets.find(
        (wrap) => wrap.dataset.metric === metric,
      );
    }

    _findChartCanvas(metric) {
      return this.chartCanvasTargets.find(
        (canvas) => canvas.dataset.metric === metric,
      );
    }

    _destroyChart(metric) {
      destroyAnalyticsChart(this.state.charts[metric]);
      delete this.state.charts[metric];
    }

    _destroyAllCharts() {
      METRICS.forEach((metric) => this._destroyChart(metric));
    }
  }

  application.register("route-analytics", RouteAnalyticsController);
})();
