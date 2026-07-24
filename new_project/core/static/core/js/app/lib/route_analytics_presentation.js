import { escapeHtml } from "./dom.js";

export const ROUTE_ANALYTICS_METRICS = ["count", "money", "volume", "turnover"];

const TOP_CHART_GROUPS = 15;
const OTHER_LABEL = "Прочие";

const PIE_COLORS = [
  "rgba(6, 57, 113, 0.90)",
  "rgba(6, 57, 113, 0.75)",
  "rgba(30, 90, 150, 0.80)",
  "rgba(55, 120, 180, 0.75)",
  "rgba(80, 145, 200, 0.70)",
  "rgba(110, 165, 210, 0.70)",
  "rgba(140, 180, 215, 0.75)",
  "rgba(90, 110, 130, 0.70)",
  "rgba(120, 135, 150, 0.65)",
  "rgba(70, 95, 120, 0.80)",
  "rgba(45, 75, 110, 0.75)",
  "rgba(20, 65, 120, 0.70)",
  "rgba(100, 155, 195, 0.65)",
  "rgba(160, 185, 210, 0.70)",
  "rgba(50, 50, 60, 0.55)",
  "rgba(90, 90, 100, 0.50)",
];

function formatCompactValue(value, unit) {
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

function registerDataLabelsPlugin() {
  const ChartDataLabelsPlugin =
    window.ChartDataLabels || window.ChartDataLabelsPlugin || null;
  if (ChartDataLabelsPlugin && window.Chart) {
    window.Chart.register(ChartDataLabelsPlugin);
  }
}

export function buildChartRows(rows, unit) {
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
    totalValue > 0 ? ((otherValue / totalValue) * 100).toFixed(1) : "0.0";

  top.push({
    label: OTHER_LABEL,
    value: otherValue,
    value_display: formatCompactValue(otherValue, unit),
    share_pct: sharePct,
  });

  return top;
}

export function renderAnalyticsTable(tableWrap, data) {
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

export function renderAnalyticsNestedTable(tableWrap, data) {
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
      const rowClass =
        row.is_total || row.is_subtotal
          ? "fw-bold route-analytics-row-subtotal"
          : "";
      return `
        <tr class="${rowClass}">
          <td>${escapeHtml(row.outer_label || "")}</td>
          <td>${escapeHtml(row.inner_label || "")}</td>
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
            <th>${escapeHtml(data.dimension_label || "Группа")}</th>
            <th>${escapeHtml(data.dimension_inner_label || "Внутри")}</th>
            <th class="text-end">Значение${unit ? `, ${escapeHtml(unit)}` : ""}</th>
            <th class="text-end">Доля, %</th>
          </tr>
        </thead>
        <tbody>${body}</tbody>
      </table>
    </div>
  `;
}

function resolveDrillLabel(chart, event, elements, chartRows) {
  if (elements && elements.length) {
    const index = elements[0].index;
    return chartRows[index]?.label || null;
  }

  const yScale = chart.scales?.y;
  if (yScale && typeof yScale.getValueForPixel === "function") {
    const index = yScale.getValueForPixel(event.y);
    if (Number.isInteger(index) && chartRows[index]) {
      return chartRows[index].label;
    }
  }

  return null;
}

function makeDrillClickHandler(chartRows, options) {
  const { onDrillDown, drilldownEnabled } = options || {};
  if (!drilldownEnabled || typeof onDrillDown !== "function") {
    return undefined;
  }

  return (event, elements, chart) => {
    const label = resolveDrillLabel(chart, event, elements, chartRows);
    if (!label || label === OTHER_LABEL) {
      return;
    }
    onDrillDown(label);
  };
}

export function createAnalyticsBarChart(canvas, data, options = {}) {
  if (typeof window.Chart === "undefined") {
    return null;
  }

  const chartRows = buildChartRows(data.rows || [], data.unit || "");
  if (!chartRows.length) {
    return null;
  }

  registerDataLabelsPlugin();

  const labels = chartRows.map((row) => row.label);
  const values = chartRows.map((row) => Number(row.value) || 0);
  const drilldownEnabled = Boolean(options.drilldownEnabled);
  canvas.style.cursor = drilldownEnabled ? "pointer" : "default";

  const ctx = canvas.getContext("2d");
  return new window.Chart(ctx, {
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
      onClick: makeDrillClickHandler(chartRows, options),
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

export function createAnalyticsPieChart(canvas, data, options = {}) {
  if (typeof window.Chart === "undefined") {
    return null;
  }

  const chartRows = buildChartRows(data.rows || [], data.unit || "");
  if (!chartRows.length) {
    return null;
  }

  registerDataLabelsPlugin();

  const labels = chartRows.map((row) => row.label);
  const values = chartRows.map((row) => Number(row.value) || 0);
  const colors = chartRows.map(
    (_row, index) => PIE_COLORS[index % PIE_COLORS.length],
  );
  const drilldownEnabled = Boolean(options.drilldownEnabled);
  canvas.style.cursor = drilldownEnabled ? "pointer" : "default";

  const ctx = canvas.getContext("2d");
  return new window.Chart(ctx, {
    type: "pie",
    data: {
      labels,
      datasets: [
        {
          data: values,
          backgroundColor: colors,
          borderWidth: 1,
          borderColor: "#ffffff",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      onClick: (event, elements, chart) => {
        if (!drilldownEnabled || typeof options.onDrillDown !== "function") {
          return;
        }
        if (!elements || !elements.length) {
          return;
        }
        const label = chartRows[elements[0].index]?.label;
        if (!label || label === OTHER_LABEL) {
          return;
        }
        options.onDrillDown(label);
      },
      plugins: {
        legend: {
          position: "right",
          labels: {
            boxWidth: 12,
            font: { size: 11 },
          },
        },
        datalabels: {
          color: "#ffffff",
          font: { size: 11, weight: "600" },
          formatter: (_value, context) => {
            const row = chartRows[context.dataIndex];
            if (!row) return "";
            const pct = Number(row.share_pct);
            if (!Number.isFinite(pct) || pct < 3) {
              return "";
            }
            return `${row.share_pct}%`;
          },
        },
      },
    },
  });
}

export function destroyAnalyticsChart(chart) {
  if (chart) {
    chart.destroy();
  }
}

export function renderLoadingTable(tableWrap) {
  tableWrap.classList.add("route-analytics-table-wrap--loading");
  tableWrap.innerHTML = `
    <div class="route-analytics-table-loading text-muted">
      <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
      Загрузка...
    </div>
  `;
}
