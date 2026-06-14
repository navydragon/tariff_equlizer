import { fetchJson } from "../lib/http.js";
import { escapeHtml } from "../lib/dom.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus is not available for route-analytics.");
    return;
  }

  const TOP_CHART_GROUPS = 15;
  const METRICS = ["count", "money", "volume", "turnover"];

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

      tableWrap.classList.add("route-analytics-table-wrap--loading");
      tableWrap.innerHTML = `
        <div class="route-analytics-table-loading text-muted">
          <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
          Загрузка...
        </div>
      `;

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
        this._renderTable(tableWrap, data);
        this._renderChart(metric, chartCanvas, data);
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

    _renderTable(tableWrap, data) {
      const rows = Array.isArray(data.rows) ? data.rows : [];
      const unit = data.unit || "";

      if (!rows.length) {
        tableWrap.classList.remove("route-analytics-table-wrap--loading");
        tableWrap.innerHTML =
          '<div class="text-muted py-4 text-center">Нет данных для таблицы.</div>';
        return;
      }

      const body = rows
        .map((row) => {
          const rowClass = row.is_total ? "fw-bold" : "";
          return `
            <tr class="${rowClass}">
              <td>${escapeHtml(row.label || "")}</td>
              <td class="text-end">${escapeHtml(row.value_display || "")}</td>
              <td class="text-end">${escapeHtml(row.share_pct || "0.0")}%</td>
            </tr>
          `;
        })
        .join("");

      tableWrap.classList.remove("route-analytics-table-wrap--loading");
      tableWrap.innerHTML = `
        <div class="table-responsive">
          <table class="table table-sm table-vcenter">
            <thead>
              <tr>
                <th>${escapeHtml(data.dimension_label || "Категория")}</th>
                <th class="text-end">Значение${unit ? `, ${escapeHtml(unit)}` : ""}</th>
                <th class="text-end">Доля, %</th>
              </tr>
            </thead>
            <tbody>${body}</tbody>
          </table>
        </div>
      `;
    }

    _renderChart(metric, canvas, data) {
      if (typeof window.Chart === "undefined") {
        return;
      }

      this._destroyChart(metric);

      const chartRows = this._buildChartRows(data.rows || [], data.unit || "");
      if (!chartRows.length) {
        return;
      }

      const labels = chartRows.map((row) => row.label);
      const values = chartRows.map((row) => Number(row.value) || 0);

      const ChartDataLabelsPlugin =
        window.ChartDataLabels || window.ChartDataLabelsPlugin || null;
      if (ChartDataLabelsPlugin && window.Chart) {
        window.Chart.register(ChartDataLabelsPlugin);
      }

      const ctx = canvas.getContext("2d");
      this.state.charts[metric] = new window.Chart(ctx, {
        type: "bar",
        data: {
          labels,
          datasets: [
            {
              label: data.unit || "",
              data: values,
              backgroundColor: "rgba(6, 57, 113, 0.75)",
              borderRadius: 4,
              maxBarThickness: 28,
            },
          ],
        },
        options: {
          indexAxis: "y",
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            datalabels: {
              anchor: "end",
              align: "right",
              color: "#1f2937",
              font: { size: 11, weight: "600" },
              formatter: (_value, context) => {
                const row = chartRows[context.dataIndex];
                return row ? row.value_display : "";
              },
            },
          },
          scales: {
            x: {
              display: false,
              grid: { display: false },
            },
            y: {
              grid: { display: false },
            },
          },
        },
      });
    }

    _buildChartRows(rows, unit) {
      const dataRows = rows.filter((row) => !row.is_total);
      const sorted = [...dataRows].sort(
        (a, b) => (Number(b.value) || 0) - (Number(a.value) || 0),
      );

      if (sorted.length <= TOP_CHART_GROUPS) {
        return sorted;
      }

      const top = sorted.slice(0, TOP_CHART_GROUPS);
      const rest = sorted.slice(TOP_CHART_GROUPS);
      const otherValue = rest.reduce(
        (sum, row) => sum + (Number(row.value) || 0),
        0,
      );
      const total = rows.find((row) => row.is_total);
      const totalValue = total ? Number(total.value) || 0 : 0;
      const sharePct =
        totalValue > 0
          ? ((otherValue / totalValue) * 100).toFixed(1)
          : "0.0";

      top.push({
        label: "Прочие",
        value: otherValue,
        value_display: this._formatCompactValue(otherValue, unit),
        share_pct: sharePct,
      });

      return top;
    }

    _formatCompactValue(value, unit) {
      if (unit.includes("шт")) {
        return String(Math.round(value));
      }
      if (value >= 1_000_000_000) {
        return (value / 1_000_000_000).toFixed(2);
      }
      if (value >= 1_000_000) {
        return (value / 1_000_000).toFixed(2);
      }
      return value.toFixed(2);
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
      const chart = this.state.charts[metric];
      if (chart) {
        chart.destroy();
        delete this.state.charts[metric];
      }
    }

    _destroyAllCharts() {
      METRICS.forEach((metric) => this._destroyChart(metric));
    }
  }

  application.register("route-analytics", RouteAnalyticsController);
})();
