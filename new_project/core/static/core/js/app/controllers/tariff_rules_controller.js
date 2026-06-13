import { fetchJson } from "../lib/http.js";
import { escapeHtml } from "../lib/dom.js";
import { renderErrors } from "../lib/errors.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for tariff-rules.");
    return;
  }

  const PARAMETERS = [
    { code: "cargo_group", label: "Группа груза", type: "choice" },
    { code: "cargo_code", label: "Код груза", type: "choice" },
    { code: "origin_railroad", label: "Дорога отправления", type: "choice" },
    { code: "destination_railroad", label: "Дорога назначения", type: "choice" },
    { code: "wagon_kind", label: "Род вагона", type: "choice" },
    { code: "shipment_type", label: "Тип отправки", type: "choice" },
    { code: "message_type", label: "Вид сообщения", type: "choice" },
    { code: "shipper", label: "Грузоотправитель", type: "choice" },
    { code: "shipper_holding", label: "Холдинг грузоотправителя", type: "choice" },
    { code: "distance_belt", label: "Пояс дальности", type: "choice" },
  ];

  const OPERATORS = [
    { code: "include", label: "включает" },
    { code: "exclude", label: "не включает" },
    { code: "lt", label: "<" },
    { code: "gt", label: ">" },
  ];

  function buildUrl(template, id) {
    return String(template || "").replace("/0/", "/" + String(id) + "/");
  }

  function parameterLabel(code) {
    const item = PARAMETERS.find((p) => p.code === code);
    return item ? item.label : code || "—";
  }

  function operatorLabel(code) {
    const item = OPERATORS.find((o) => o.code === code);
    return item ? item.label : code || "";
  }

  function isDistanceBeltThreshold(parameter, operator) {
    return parameter === "distance_belt" && (operator === "lt" || operator === "gt");
  }

  function usesNumericConditionValue(parameter, operator) {
    const meta = PARAMETERS.find((p) => p.code === parameter);
    return (meta && meta.type === "numeric") || isDistanceBeltThreshold(parameter, operator);
  }

  function normalizeOptionItems(items) {
    return (items || []).map((item) => ({
      value: String(item.value),
      text: item.text != null ? String(item.text) : String(item.value),
    }));
  }

  function normalizeConditionValues(values) {
    if (Array.isArray(values)) {
      return values.map((value) => String(value));
    }
    if (values == null || values === "") {
      return [];
    }
    return [String(values)];
  }

  function formatConditionValues(condition, labelResolver) {
    const meta = PARAMETERS.find((p) => p.code === condition.parameter);
    const values = condition.values;
    if (usesNumericConditionValue(condition.parameter, condition.operator)) {
      if (values == null || values === "") return "—";
      return String(values);
    }
    const list = Array.isArray(condition.values_display) && condition.values_display.length
      ? condition.values_display.map((value) => String(value))
      : normalizeConditionValues(values);
    if (!list.length) return "—";
    const text = list
      .map((value) => {
        if (typeof labelResolver === "function") {
          const resolved = labelResolver(condition.parameter, value);
          if (resolved) return resolved;
        }
        return value;
      })
      .join(", ");
    return text.length > 80 ? `${text.slice(0, 77)}…` : text;
  }

  function formatConditionsSummary(conditions, labelResolver) {
    if (!conditions || !conditions.length) {
      return '<span class="text-muted">Все маршруты набора (без фильтра)</span>';
    }
    const sorted = [...conditions].sort(
      (a, b) => (a.position || 0) - (b.position || 0),
    );
    return sorted
      .map((condition) => {
        const param = escapeHtml(parameterLabel(condition.parameter));
        const op = escapeHtml(operatorLabel(condition.operator));
        const vals = escapeHtml(formatConditionValues(condition, labelResolver));
        return `<div class="tariff-rule-condition-line"><span class="fw-medium">${param}</span> ${op}: ${vals}</div>`;
      })
      .join("");
  }

  function formatYearValuesSummary(yearValues, startYear, endYear) {
    if (!yearValues || !yearValues.length) {
      return '<span class="text-muted">—</span>';
    }
    const byYear = new Map(
      yearValues.map((item) => [String(item.year), String(item.coefficient)]),
    );
    const years = [];
    const start = startYear || 2025;
    const end = endYear || start;
    for (let year = start; year <= end; year += 1) {
      years.push(year);
    }

    const nonDefault = years
      .map((year) => {
        const coef = byYear.get(String(year)) || "1";
        const numeric = parseFloat(coef);
        const isDefault =
          !Number.isFinite(numeric) || Math.abs(numeric - 1) < 1e-6;
        return { year, coef, isDefault };
      })
      .filter((item) => !item.isDefault);

    if (!nonDefault.length) {
      return '<span class="text-muted">1,000 — без изменений</span>';
    }

    return nonDefault
      .map(
        (item) =>
          `<span class="badge bg-blue-lt me-1 mb-1">${item.year}: ${escapeHtml(item.coef)}</span>`,
      )
      .join("");
  }

  class TariffRulesController extends Stimulus.Controller {
    static targets = [
      "tbody",
      "summary",
      "modal",
      "modalTitle",
      "errors",
      "name",
      "conditions",
      "coverage",
      "basePercentRange",
      "basePercentInput",
      "years",
      "saveBtn",
    ];

    static values = {
      scenarioId: Number,
      listUrl: String,
      createUrl: String,
      detailUrlTemplate: String,
      updateUrlTemplate: String,
      deleteUrlTemplate: String,
      optionsUrlTemplate: String,
      statsUrl: String,
      startYear: Number,
      endYear: Number,
    };

    connect() {
      this.state = {
        rules: [],
        editingRuleId: null,
        optionLabels: new Map(),
        editLoadId: 0,
        suppressCoverageRefresh: false,
      };
      this.statsDebounceTimer = null;

      this.modalInstance = null;
      this.ensureModal();
      this.initYearsGrid();
      this.setBasePercent(100);
      this.loadRules();
    }

    // === List ===
    async loadRules() {
      if (this.hasSummaryTarget) this.summaryTarget.textContent = "Загрузка...";
      const { data } = await fetchJson(this.listUrlValue, { method: "GET" });
      if (!data || !data.success) {
        this.renderListError((data && (data.errors || [data.error])) || ["Ошибка загрузки"]);
        return;
      }
      this.state.rules = data.rules || [];
      await this.ensureOptionLabelsForRules(this.state.rules);
      this.renderTable();
      if (this.hasSummaryTarget) {
        this.summaryTarget.textContent = this.state.rules.length
          ? `Всего: ${this.state.rules.length}`
          : "Пока нет правил";
      }
    }

    renderListError(errors) {
      this.tbodyTarget.innerHTML = `<tr><td colspan="6" class="text-danger">${escapeHtml(
        (errors || []).join(", "),
      )}</td></tr>`;
      if (this.hasSummaryTarget) this.summaryTarget.textContent = "";
    }

    renderTable() {
      if (!this.state.rules.length) {
        this.tbodyTarget.innerHTML =
          '<tr><td colspan="6" class="text-muted">Нет тарифных решений</td></tr>';
        return;
      }

      const startYear = this.startYearValue || 2025;
      const endYear = this.endYearValue || startYear;

      this.tbodyTarget.innerHTML = this.state.rules
        .map((r, idx) => {
          const bp = r.base_percent != null ? String(r.base_percent) : "";
          const conditionsHtml = formatConditionsSummary(
            r.conditions || [],
            (parameter, value) => this.resolveOptionLabel(parameter, value),
          );
          const yearsHtml = formatYearValuesSummary(
            r.year_values || [],
            startYear,
            endYear,
          );
          return `
            <tr data-rule-id="${r.id}">
              <td class="text-muted">${idx + 1}</td>
              <td class="fw-medium">${escapeHtml(r.name || "")}</td>
              <td class="small">${conditionsHtml}</td>
              <td class="small">${yearsHtml}</td>
              <td>${escapeHtml(bp)}</td>
              <td class="text-end">
                <div class="btn-list justify-content-end">
                  <button type="button" class="btn btn-sm btn-outline-primary" data-action="tariff-rules#openEdit" data-rule-id="${r.id}">
                    <i class="ti ti-edit"></i>
                    Редактировать
                  </button>
                  <button type="button" class="btn btn-sm btn-outline-danger" data-action="tariff-rules#deleteRule" data-rule-id="${r.id}">
                    <i class="ti ti-trash"></i>
                    Удалить
                  </button>
                </div>
              </td>
            </tr>
          `;
        })
        .join("");
    }

    // === Modal ===
    ensureModal() {
      if (!this.hasModalTarget || typeof bootstrap === "undefined") return;
      this.modalInstance = bootstrap.Modal.getOrCreateInstance(this.modalTarget);
    }

    openCreate() {
      this.state.editLoadId += 1;
      this.state.editingRuleId = null;
      this.modalTitleTarget.textContent = "Добавить тарифное решение";
      this.clearErrors();
      this.nameTarget.value = "";
      this.setBasePercent(100);
      this.conditionsTarget.innerHTML = "";
      this.resetYearInputs();
      this.updateCoverageText(null);
      this.modalInstance.show();
    }

    async openEdit(event) {
      const ruleId = parseInt(event.currentTarget.dataset.ruleId || "0", 10);
      if (!ruleId) return;
      this.state.editLoadId += 1;
      const loadId = this.state.editLoadId;
      this.state.editingRuleId = ruleId;
      this.modalTitleTarget.textContent = "Редактировать тарифное решение";
      this.clearErrors();
      this.conditionsTarget.innerHTML = "";
      this.resetYearInputs();
      this.updateCoverageText("loading");
      this.modalInstance.show();

      const url = buildUrl(this.detailUrlTemplateValue, ruleId);
      const { data } = await fetchJson(url, { method: "GET" });
      if (!data || !data.success) {
        this.showErrors((data && (data.errors || [data.error])) || ["Ошибка загрузки"]);
        return;
      }

      const rule = data.rule;
      this.nameTarget.value = rule.name || "";
      this.setBasePercent(parseFloat(rule.base_percent || "100"));
      this.applyYearValues(rule.year_values || []);

      void this.populateEditConditions(rule, loadId);
    }

    async populateEditConditions(rule, loadId) {
      this.state.suppressCoverageRefresh = true;
      try {
        await this.ensureOptionLabelsForRules([rule]);
        if (loadId !== this.state.editLoadId) return;

        this.conditionsTarget.innerHTML = "";
        for (const condition of rule.conditions || []) {
          if (loadId !== this.state.editLoadId) return;
          await this.addConditionRow(condition);
        }
      } finally {
        if (loadId !== this.state.editLoadId) return;
        this.state.suppressCoverageRefresh = false;
        await this.refreshCoverage();
      }
    }

    clearErrors() {
      if (this.hasErrorsTarget) this.errorsTarget.innerHTML = "";
    }

    showErrors(errors) {
      if (!this.hasErrorsTarget) return;
      const div = document.createElement("div");
      div.className = "alert alert-danger";
      this.errorsTarget.appendChild(div);
      renderErrors(div, errors || []);
    }

    // === Conditions ===
    addCondition() {
      void this.addConditionRow(null);
    }

    async addConditionRow(condition) {
      const row = document.createElement("div");
      row.className = "row g-2 align-items-start mb-2 tariff-rule-condition-row";
      row.dataset.conditionRow = "1";

      const parameterOptions = PARAMETERS.map(
        (p) => `<option value="${p.code}">${escapeHtml(p.label)}</option>`,
      ).join("");
      const operatorOptions = OPERATORS.map(
        (o) => `<option value="${o.code}">${escapeHtml(o.label)}</option>`,
      ).join("");

      row.innerHTML = `
        <div class="col-12 col-lg-4">
          <label class="form-label">Параметр</label>
          <select class="form-select" data-condition-parameter>
            <option value="">Выберите...</option>
            ${parameterOptions}
          </select>
        </div>
        <div class="col-6 col-lg-2">
          <label class="form-label">Оператор</label>
          <select class="form-select" data-condition-operator>
            ${operatorOptions}
          </select>
        </div>
        <div class="col-12 col-lg-5" data-condition-values-wrap>
          <label class="form-label">Значения</label>
          <div data-condition-values></div>
        </div>
        <div class="col-auto col-lg-1 tariff-rule-condition-delete">
          <button type="button" class="btn btn-outline-danger" data-action="tariff-rules#removeCondition" title="Удалить условие">
            <i class="ti ti-x"></i>
          </button>
        </div>
      `;

      this.conditionsTarget.appendChild(row);

      const parameterSelect = row.querySelector("[data-condition-parameter]");
      const operatorSelect = row.querySelector("[data-condition-operator]");
      parameterSelect.addEventListener("change", () => this.onConditionParameterChange(row));
      operatorSelect.addEventListener("change", () => this.onConditionOperatorChange(row));

      const parameter = condition && condition.parameter ? condition.parameter : "";
      const operator = condition && condition.operator ? condition.operator : "include";
      const values = condition ? condition.values : null;

      if (parameter) parameterSelect.value = parameter;
      operatorSelect.value = operator;

      await this.renderConditionValueEditor(row, parameter, operator, values);
    }

    removeCondition(event) {
      const row = event.currentTarget.closest("[data-condition-row]");
      if (row) row.remove();
      this.refreshCoverageDebounced();
    }

    async onConditionParameterChange(row) {
      const parameter = row.querySelector("[data-condition-parameter]").value;
      const operator = row.querySelector("[data-condition-operator]").value;
      await this.renderConditionValueEditor(row, parameter, operator, null);
    }

    async onConditionOperatorChange(row) {
      const parameter = row.querySelector("[data-condition-parameter]").value;
      const operator = row.querySelector("[data-condition-operator]").value;
      const currentValues = this.readConditionValues(row, parameter, operator);
      await this.renderConditionValueEditor(row, parameter, operator, currentValues);
    }

    async loadOptions(parameter) {
      try {
        const url = this.optionsUrlTemplateValue + "?parameter=" + encodeURIComponent(parameter);
        const { data } = await fetchJson(url, { method: "GET" });
        if (!data || !data.success) return [];
        const items = normalizeOptionItems(data.items || []);
        const labelMap = new Map(
          items.map((item) => [String(item.value), item.text]),
        );
        this.state.optionLabels.set(parameter, labelMap);
        return items;
      } catch (_e) {
        return [];
      }
    }

    resolveOptionLabel(parameter, value) {
      const labels = this.state.optionLabels.get(parameter);
      if (!labels) return null;
      return labels.get(String(value)) || null;
    }

    async ensureOptionLabelsForRules(rules) {
      const parameters = new Set(
        (rules || []).flatMap((rule) =>
          (rule.conditions || []).map((condition) => condition.parameter),
        ),
      );
      await Promise.all(
        Array.from(parameters)
          .filter(Boolean)
          .map((parameter) => this.loadOptions(parameter)),
      );
    }

    async renderConditionValueEditor(row, parameter, operator, values) {
      const container = row.querySelector("[data-condition-values]");
      if (!container) return;
      container.innerHTML = "";

      const isNumeric = usesNumericConditionValue(parameter, operator);

      if (!parameter) {
        container.innerHTML = '<div class="text-muted">Сначала выберите параметр</div>';
        return;
      }

      if (isNumeric) {
        const input = document.createElement("input");
        input.type = "number";
        input.className = "form-control";
        input.placeholder = isDistanceBeltThreshold(parameter, operator)
          ? "Середина пояса, км"
          : "Введите число";
        input.dataset.conditionNumber = "1";
        input.addEventListener("input", () => this.refreshCoverageDebounced());
        if (values != null && values !== "" && !Array.isArray(values)) {
          input.value = String(values);
        }
        container.appendChild(input);
        if (isDistanceBeltThreshold(parameter, operator)) {
          const hint = document.createElement("div");
          hint.className = "form-text text-muted";
          hint.textContent =
            "Сравнивается середина интервала пояса, например 500–1000 → 750 км";
          container.appendChild(hint);
        }
        this.refreshCoverageDebounced();
        return;
      }

      const select = document.createElement("select");
      select.className = "form-select";
      select.multiple = true;
      select.dataset.conditionSelect = "1";
      container.appendChild(select);

      const ts = new TomSelect(select, {
        plugins: ["remove_button", "clear_button"],
        persist: false,
        valueField: "value",
        labelField: "text",
        searchField: ["text"],
        preload: false,
      });
      select._tomselect = ts;

      const initial = normalizeConditionValues(values);
      const items = await this.loadOptions(parameter);
      const byValue = new Map(items.map((item) => [String(item.value), item]));
      initial.forEach((value) => {
        if (!byValue.has(value)) {
          const fallbackText = this.resolveOptionLabel(parameter, value) || value;
          ts.addOption({ value, text: fallbackText });
          byValue.set(value, { value, text: fallbackText });
        }
      });
      ts.addOptions(items);
      ts.refreshOptions(false);
      if (initial.length) {
        ts.setValue(initial, true);
      }
      ts.on("change", () => this.refreshCoverageDebounced());
      this.refreshCoverageDebounced();
    }

    readConditionValues(row, parameter, operator) {
      const op =
        operator || row.querySelector("[data-condition-operator]")?.value || "";
      if (usesNumericConditionValue(parameter, op)) {
        const input = row.querySelector("[data-condition-number]");
        return input ? input.value : null;
      }
      const select = row.querySelector("[data-condition-select]");
      if (select && select._tomselect) {
        return select._tomselect.getValue();
      }
      return [];
    }

    collectConditions() {
      const rows = Array.from(this.conditionsTarget.querySelectorAll("[data-condition-row]"));
      return rows
        .map((row, idx) => {
          const parameter = row.querySelector("[data-condition-parameter]").value;
          const operator = row.querySelector("[data-condition-operator]").value;
          if (!parameter) return null;
          const values = this.readConditionValues(row, parameter, operator);
          const normalized = usesNumericConditionValue(parameter, operator)
              ? (values == null || values === "" ? null : Number(values))
              : Array.isArray(values)
                ? values
                : values != null
                  ? [values]
                  : [];
          return {
            position: idx,
            parameter,
            operator,
            values: normalized,
          };
        })
        .filter(Boolean);
    }

    // === Base percent ===
    setBasePercent(val) {
      const num = isFinite(val) ? Math.max(0, Math.min(200, Math.round(val))) : 100;
      if (this.hasBasePercentRangeTarget) this.basePercentRangeTarget.value = String(num);
      if (this.hasBasePercentInputTarget) this.basePercentInputTarget.value = String(num);
    }

    syncBasePercentFromRange() {
      this.setBasePercent(parseFloat(this.basePercentRangeTarget.value || "100"));
    }

    syncBasePercentFromInput() {
      this.setBasePercent(parseFloat(this.basePercentInputTarget.value || "100"));
    }

    // === Coverage stats ===
    updateCoverageText(payload) {
      if (!this.hasCoverageTarget) return;
      if (payload === "loading") {
        this.coverageTarget.textContent = "Покрытие по маршрутам: расчёт…";
        return;
      }
      if (!payload) {
        this.coverageTarget.textContent = "Покрытие по маршрутам: —";
        return;
      }
      const pct = payload.matched_percent != null ? String(payload.matched_percent) : "0";
      const matched = payload.matched_routes != null ? String(payload.matched_routes) : "0";
      const total = payload.total_routes != null ? String(payload.total_routes) : "0";
      this.coverageTarget.textContent = `Покрытие по маршрутам: ${pct}% (${matched} из ${total})`;
    }

    refreshCoverageDebounced() {
      if (this.state.suppressCoverageRefresh) return;
      if (this.statsDebounceTimer) window.clearTimeout(this.statsDebounceTimer);
      this.statsDebounceTimer = window.setTimeout(() => this.refreshCoverage(), 250);
    }

    async refreshCoverage() {
      if (!this.statsUrlValue) return;
      if (!this.hasCoverageTarget) return;
      const payload = { conditions: this.collectConditions() };
      const { data } = await fetchJson(this.statsUrlValue, { method: "POST", body: payload });
      if (!data || !data.success) {
        this.updateCoverageText(null);
        return;
      }
      this.updateCoverageText(data);
    }

    // === Years grid ===
    initYearsGrid() {
      if (!this.hasYearsTarget) return;
      const start = this.startYearValue || 2025;
      const end = this.endYearValue || start;
      const years = [];
      for (let y = start; y <= end; y += 1) years.push(y);

      this.yearsTarget.innerHTML = years
        .map(
          (y) => `
          <div class="col">
            <label class="form-label mb-1">${y}</label>
            <input type="number" step="0.0001" class="form-control" value="1" data-year="${y}" />
          </div>
        `,
        )
        .join("");
    }

    resetYearInputs() {
      this.yearsTarget.querySelectorAll("input[data-year]").forEach((el) => {
        el.value = "1";
      });
    }

    applyYearValues(yearValues) {
      const map = new Map(
        (yearValues || []).map((v) => [String(v.year), String(v.coefficient)]),
      );
      this.yearsTarget.querySelectorAll("input[data-year]").forEach((el) => {
        const year = String(el.dataset.year);
        if (map.has(year)) el.value = map.get(year);
      });
    }

    collectYearValues() {
      const result = {};
      this.yearsTarget.querySelectorAll("input[data-year]").forEach((el) => {
        const year = String(el.dataset.year);
        const val = String(el.value || "").trim();
        if (val !== "") result[year] = val;
      });
      return result;
    }

    // === Save/Delete ===
    async save() {
      this.clearErrors();
      const payload = {
        name: this.nameTarget.value || "",
        base_percent: this.basePercentInputTarget.value || "100",
        conditions: this.collectConditions(),
        year_values: this.collectYearValues(),
      };

      const isEdit = !!this.state.editingRuleId;
      const url = isEdit
        ? buildUrl(this.updateUrlTemplateValue, this.state.editingRuleId)
        : this.createUrlValue;

      const { data } = await fetchJson(url, { method: "POST", body: payload });
      if (!data || !data.success) {
        this.showErrors((data && (data.errors || (data.error ? [data.error] : null))) || [
          "Ошибка сохранения",
        ]);
        this.showToast("error", "Ошибка сохранения");
        return;
      }

      this.modalInstance.hide();
      await this.loadRules();
      this.showToast("success", "Сохранено");
      this._dispatchTariffRulesChanged();
    }

    async deleteRule(event) {
      const ruleId = parseInt(event.currentTarget.dataset.ruleId || "0", 10);
      if (!ruleId) return;
      const ok = window.confirm("Удалить тарифное решение?");
      if (!ok) return;
      const url = buildUrl(this.deleteUrlTemplateValue, ruleId);
      const { data } = await fetchJson(url, { method: "POST", body: {} });
      if (!data || !data.success) {
        this.showToast("error", "Ошибка удаления");
        return;
      }
      await this.loadRules();
      this.showToast("success", "Удалено");
      this._dispatchTariffRulesChanged();
    }

    _dispatchTariffRulesChanged() {
      if (!this.hasScenarioIdValue) return;
      document.dispatchEvent(
        new CustomEvent("tariff-rules-changed", {
          detail: { scenarioId: this.scenarioIdValue },
        }),
      );
    }

    showToast(type, message) {
      let toastElement;
      if (type === "success") {
        toastElement = document.getElementById("toastSuccess");
      } else {
        toastElement = document.getElementById("toastError");
        const toastBody = document.getElementById("toastErrorBody");
        if (toastBody) toastBody.textContent = message || "Ошибка";
      }
      if (toastElement && typeof bootstrap !== "undefined") {
        const toast = new bootstrap.Toast(toastElement, { autohide: true, delay: 5000 });
        toast.show();
      }
    }
  }

  application.register("tariff-rules", TariffRulesController);
})();

