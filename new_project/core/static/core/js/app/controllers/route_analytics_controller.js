import { fetchBlob, fetchJson } from "../lib/http.js";
import { escapeHtml } from "../lib/dom.js";
import {
  ROUTE_ANALYTICS_METRICS,
  createAnalyticsBarChart,
  createAnalyticsPieChart,
  destroyAnalyticsChart,
  renderAnalyticsNestedTable,
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

  function emptyDrillState() {
    return Object.fromEntries(METRICS.map((metric) => [metric, { parentLabel: null }]));
  }

  class RouteAnalyticsController extends Stimulus.Controller {
    static targets = [
      "routeSetSelect",
      "dimensionSelect",
      "dimensionInnerSelect",
      "exportButton",
      "tabPanel",
      "tableWrap",
      "chartCanvas",
      "pieCanvas",
      "drillNav",
    ];

    static values = {
      routeSetListUrl: String,
      aggregateUrl: String,
      exportUrl: String,
      debounceMs: { type: Number, default: 300 },
    };

    connect() {
      this.state = {
        routeSetId: null,
        dimension: this.hasDimensionSelectTarget
          ? this.dimensionSelectTarget.value
          : "cargo_group",
        dimensionInner: this.hasDimensionInnerSelectTarget
          ? this.dimensionInnerSelectTarget.value
          : "none",
        loadedTabs: new Set(),
        charts: {},
        filterTimer: null,
        activeMetric: "count",
        filterGeneration: 0,
        drill: emptyDrillState(),
        dimensionInnerLabel: null,
      };

      this._syncInnerOptions();
      this._updateExportButton();
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
      this.state.dimensionInner = this.hasDimensionInnerSelectTarget
        ? this.dimensionInnerSelectTarget.value
        : "none";

      this._syncInnerOptions();

      if (this.state.dimensionInner === "none") {
        this.state.dimensionInnerLabel = null;
      }

      this.state.filterGeneration += 1;
      this.state.loadedTabs.clear();
      this.state.drill = emptyDrillState();
      this._destroyAllCharts();
      this._resetAllPanes();
      this._updateExportButton();

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
      this._updateExportButton();
      this._updateDrillNav(metric);

      if (!this._filtersReady()) {
        return;
      }

      if (this.state.loadedTabs.has(metric)) {
        return;
      }

      this._loadMetric(metric);
    }

    onDrillBack(event) {
      const metric =
        event.currentTarget?.dataset?.routeAnalyticsMetricParam ||
        this.state.activeMetric;
      if (!metric || !METRICS.includes(metric)) {
        return;
      }

      if (!this.state.drill[metric]?.parentLabel) {
        return;
      }

      this.state.drill[metric].parentLabel = null;
      this.state.loadedTabs.delete(metric);
      this._loadMetric(metric, { chartsOnly: false, keepTable: true });
    }

    async onExport() {
      if (!this._filtersReady() || !this.exportUrlValue) {
        return;
      }

      const params = this._buildBaseParams(this.state.activeMetric);
      try {
        const { response, blob } = await fetchBlob(
          `${this.exportUrlValue}?${params.toString()}`,
          { method: "GET" },
        );

        if (!response.ok) {
          console.error("[route-analytics] export failed", response.status);
          return;
        }

        const disposition = response.headers.get("Content-Disposition") || "";
        const match = disposition.match(/filename="([^"]+)"/);
        const filename = match ? match[1] : "analitika_marshrutov.xlsx";

        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      } catch (error) {
        console.error("[route-analytics] export failed", error);
      }
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

    _hasInnerGrouping() {
      return this.state.dimensionInner && this.state.dimensionInner !== "none";
    }

    _syncInnerOptions() {
      if (!this.hasDimensionInnerSelectTarget) return;

      const outer = this.state.dimension;
      const select = this.dimensionInnerSelectTarget;
      Array.from(select.options).forEach((option) => {
        if (option.value === "none") {
          option.disabled = false;
          return;
        }
        option.disabled = option.value === outer;
      });

      if (select.value === outer) {
        select.value = "none";
        this.state.dimensionInner = "none";
      }
    }

    _updateExportButton() {
      if (!this.hasExportButtonTarget) return;
      this.exportButtonTarget.disabled = !this._filtersReady();
    }

    _buildBaseParams(metric) {
      const params = new URLSearchParams();
      params.set("route_set_id", String(this.state.routeSetId));
      params.set("dimension", this.state.dimension);
      params.set("metric", metric);
      if (this._hasInnerGrouping()) {
        params.set("dimension_inner", this.state.dimensionInner);
      }
      return params;
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

        this._updateDrillNav(metric);
      });
    }

    async _loadMetric(metric, options = {}) {
      if (!this._filtersReady()) {
        return;
      }

      const keepTable = Boolean(options.keepTable);
      const generation = this.state.filterGeneration;
      const panel = this._findPanel(metric);
      const tableWrap = this._findTableWrap(metric);
      const chartCanvas = this._findChartCanvas(metric);
      const pieCanvas = this._findPieCanvas(metric);
      if (!panel || !tableWrap || !chartCanvas || !pieCanvas) {
        return;
      }

      const placeholder = panel.querySelector(".route-analytics-pane-placeholder");
      const content = panel.querySelector(".route-analytics-pane-content");
      if (placeholder) placeholder.classList.add("d-none");
      if (content) content.classList.remove("d-none");

      if (!keepTable) {
        renderLoadingTable(tableWrap);
      }

      const parentLabel = this.state.drill[metric]?.parentLabel || null;
      const chartParams = this._buildBaseParams(metric);
      if (parentLabel) {
        chartParams.set("parent_filter", parentLabel);
      }

      try {
        const chartPromise = fetchJson(
          `${this.aggregateUrlValue}?${chartParams.toString()}`,
          { method: "GET" },
        );

        let tablePromise = null;
        if (!keepTable) {
          if (this._hasInnerGrouping()) {
            const nestedParams = this._buildBaseParams(metric);
            nestedParams.set("mode", "nested");
            tablePromise = fetchJson(
              `${this.aggregateUrlValue}?${nestedParams.toString()}`,
              { method: "GET" },
            );
          } else {
            tablePromise = chartPromise;
          }
        }

        const [{ data: chartData }, tableResult] = await Promise.all([
          chartPromise,
          tablePromise || Promise.resolve(null),
        ]);

        if (generation !== this.state.filterGeneration) {
          return;
        }

        if (!chartData || !chartData.success) {
          const errors = (chartData && chartData.errors) || ["Ошибка загрузки данных"];
          tableWrap.classList.remove("route-analytics-table-wrap--loading");
          tableWrap.innerHTML = `<div class="text-danger py-4 text-center">${escapeHtml(
            errors.join(", "),
          )}</div>`;
          return;
        }

        if (chartData.dimension_inner_label) {
          this.state.dimensionInnerLabel = chartData.dimension_inner_label;
        }

        if (!keepTable) {
          const tableData = tableResult?.data;
          if (!tableData || !tableData.success) {
            const errors =
              (tableData && tableData.errors) || ["Ошибка загрузки таблицы"];
            tableWrap.classList.remove("route-analytics-table-wrap--loading");
            tableWrap.innerHTML = `<div class="text-danger py-4 text-center">${escapeHtml(
              errors.join(", "),
            )}</div>`;
            return;
          }

          if (tableData.nested) {
            renderAnalyticsNestedTable(tableWrap, tableData);
            this.state.dimensionInnerLabel =
              tableData.dimension_inner_label || this.state.dimensionInnerLabel;
          } else {
            renderAnalyticsTable(tableWrap, tableData);
          }
        }

        this.state.loadedTabs.add(metric);
        this._renderCharts(metric, chartData);
        this._updateDrillNav(metric);
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

    _renderCharts(metric, chartData) {
      const chartCanvas = this._findChartCanvas(metric);
      const pieCanvas = this._findPieCanvas(metric);
      if (!chartCanvas || !pieCanvas) return;

      const drilldownEnabled = Boolean(chartData.drilldown_enabled);
      const onDrillDown = (label) => this._onDrillDown(metric, label);

      this._destroyChart(metric);
      this.state.charts[metric] = {
        bar: createAnalyticsBarChart(chartCanvas, chartData, {
          drilldownEnabled,
          onDrillDown,
        }),
        pie: createAnalyticsPieChart(pieCanvas, chartData, {
          drilldownEnabled,
          onDrillDown,
        }),
      };
    }

    _onDrillDown(metric, label) {
      if (!this._hasInnerGrouping()) {
        return;
      }
      if (this.state.drill[metric]?.parentLabel) {
        return;
      }

      this.state.drill[metric].parentLabel = label;
      this.state.loadedTabs.delete(metric);
      this._loadMetric(metric, { keepTable: true });
    }

    _updateDrillNav(metric) {
      const nav = this._findDrillNav(metric);
      if (!nav) return;

      const parentLabel = this.state.drill[metric]?.parentLabel || null;
      const breadcrumb = nav.querySelector('[data-role="breadcrumb"]');

      if (!parentLabel) {
        nav.classList.add("d-none");
        if (breadcrumb) breadcrumb.textContent = "";
        return;
      }

      nav.classList.remove("d-none");
      if (breadcrumb) {
        const innerLabel =
          this.state.dimensionInnerLabel ||
          (this.hasDimensionInnerSelectTarget
            ? this.dimensionInnerSelectTarget.selectedOptions[0]?.textContent
            : "") ||
          "";
        breadcrumb.textContent = innerLabel
          ? `${parentLabel} → ${innerLabel}`
          : parentLabel;
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

    _findPieCanvas(metric) {
      return this.pieCanvasTargets.find(
        (canvas) => canvas.dataset.metric === metric,
      );
    }

    _findDrillNav(metric) {
      return this.drillNavTargets.find((nav) => nav.dataset.metric === metric);
    }

    _destroyChart(metric) {
      const pair = this.state.charts[metric];
      if (pair) {
        destroyAnalyticsChart(pair.bar);
        destroyAnalyticsChart(pair.pie);
      }
      delete this.state.charts[metric];
    }

    _destroyAllCharts() {
      METRICS.forEach((metric) => this._destroyChart(metric));
    }
  }

  application.register("route-analytics", RouteAnalyticsController);
})();
