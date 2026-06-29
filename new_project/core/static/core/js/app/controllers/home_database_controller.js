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
    console.error("Stimulus is not available for home-database.");
    return;
  }

  const METRICS = ROUTE_ANALYTICS_METRICS;
  const DIMENSION = "cargo_group";

  class HomeDatabaseController extends Stimulus.Controller {
    static targets = ["kpiRow", "tabPanel", "tableWrap", "chartCanvas"];

    static values = {
      totalsUrl: String,
      aggregateUrl: String,
      routeSetId: Number,
    };

    connect() {
      if (!this.routeSetIdValue) {
        return;
      }

      this.state = {
        loadedTabs: new Set(),
        charts: {},
        activeMetric: "count",
      };

      this._loadTotals();
      this._loadMetric("count");
    }

    disconnect() {
      this._destroyAllCharts();
    }

    onTabShown(event) {
      const metric = event.target?.dataset?.homeDatabaseMetricParam;
      if (!metric || !METRICS.includes(metric)) {
        return;
      }

      this.state.activeMetric = metric;
      if (this.state.loadedTabs.has(metric)) {
        return;
      }

      this._loadMetric(metric);
    }

    async _loadTotals() {
      if (!this.hasKpiRowTarget) return;

      this.kpiRowTarget.innerHTML = `
        <div class="col-12 text-center text-muted py-3">
          <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
          Загрузка показателей...
        </div>
      `;

      const params = new URLSearchParams();
      params.set("route_set_id", String(this.routeSetIdValue));

      try {
        const { data } = await fetchJson(
          `${this.totalsUrlValue}?${params.toString()}`,
          { method: "GET" },
        );

        if (!data || !data.success) {
          const errors = (data && data.errors) || ["Ошибка загрузки"];
          this.kpiRowTarget.innerHTML = `
            <div class="col-12">
              <div class="alert alert-danger mb-0">${escapeHtml(errors.join(", "))}</div>
            </div>
          `;
          return;
        }

        const cards = Array.isArray(data.cards) ? data.cards : [];
        if (!cards.length) {
          this.kpiRowTarget.innerHTML = `
            <div class="col-12 text-muted text-center py-3">Нет данных для отображения.</div>
          `;
          return;
        }

        this.kpiRowTarget.innerHTML = cards
          .map(
            (card) => `
              <div class="col-sm-6 col-lg-3">
                <div class="card card-sm">
                  <div class="card-body">
                    <div class="subheader">${escapeHtml(card.label || "")}</div>
                    <div class="d-flex align-items-baseline gap-2 mt-1">
                      <div class="h1 mb-0">${escapeHtml(card.value_display || "0")}</div>
                      <div class="text-muted">${escapeHtml(card.unit || "")}</div>
                    </div>
                  </div>
                </div>
              </div>
            `,
          )
          .join("");
      } catch (error) {
        console.error("[home-database] totals failed", error);
        this.kpiRowTarget.innerHTML = `
          <div class="col-12">
            <div class="alert alert-danger mb-0">Не удалось загрузить показатели.</div>
          </div>
        `;
      }
    }

    async _loadMetric(metric) {
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
      params.set("route_set_id", String(this.routeSetIdValue));
      params.set("dimension", DIMENSION);
      params.set("metric", metric);

      try {
        const { data } = await fetchJson(
          `${this.aggregateUrlValue}?${params.toString()}`,
          { method: "GET" },
        );

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
        console.error("[home-database] aggregate failed", error);
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

  application.register("home-database", HomeDatabaseController);
})();
