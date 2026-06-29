import { escapeHtml } from "./dom.js";

export const ROUTE_ANALYTICS_METRICS = ["count", "money", "volume", "turnover"];

const TOP_CHART_GROUPS = 15;

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
    label: "Прочие",
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

export function createAnalyticsBarChart(canvas, data) {
  if (typeof window.Chart === "undefined") {
    return null;
  }

  const chartRows = buildChartRows(data.rows || [], data.unit || "");
  if (!chartRows.length) {
    return null;
  }

  const labels = chartRows.map((row) => row.label);
  const values = chartRows.map((row) => Number(row.value) || 0);

  const ChartDataLabelsPlugin =
    window.ChartDataLabels || window.ChartDataLabelsPlugin || null;
  if (ChartDataLabelsPlugin && window.Chart) {
    window.Chart.register(ChartDataLabelsPlugin);
  }

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
