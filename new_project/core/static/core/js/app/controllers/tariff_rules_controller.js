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
    { code: "distance_loaded_km", label: "Расстояние груж., км", type: "numeric" },
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
      this.renderTable();
      if (this.hasSummaryTarget) {
        this.summaryTarget.textContent = this.state.rules.length
          ? `Всего: ${this.state.rules.length}`
          : "Пока нет правил";
      }
    }

    renderListError(errors) {
      this.tbodyTarget.innerHTML = `<tr><td colspan="4" class="text-danger">${escapeHtml(
        (errors || []).join(", "),
      )}</td></tr>`;
      if (this.hasSummaryTarget) this.summaryTarget.textContent = "";
    }

    renderTable() {
      if (!this.state.rules.length) {
        this.tbodyTarget.innerHTML =
          '<tr><td colspan="4" class="text-muted">Нет тарифных решений</td></tr>';
        return;
      }

      this.tbodyTarget.innerHTML = this.state.rules
        .map((r, idx) => {
          const bp = r.base_percent != null ? String(r.base_percent) : "";
          return `
            <tr data-rule-id="${r.id}">
              <td class="text-muted">${idx + 1}</td>
              <td>${escapeHtml(r.name || "")}</td>
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
      this.state.editingRuleId = ruleId;
      this.modalTitleTarget.textContent = "Редактировать тарифное решение";
      this.clearErrors();
      this.conditionsTarget.innerHTML = "";
      this.resetYearInputs();

      const url = buildUrl(this.detailUrlTemplateValue, ruleId);
      const { data } = await fetchJson(url, { method: "GET" });
      if (!data || !data.success) {
        this.showErrors((data && (data.errors || [data.error])) || ["Ошибка загрузки"]);
        this.modalInstance.show();
        return;
      }

      const rule = data.rule;
      this.nameTarget.value = rule.name || "";
      this.setBasePercent(parseFloat(rule.base_percent || "100"));
      (rule.conditions || []).forEach((c) => this.addConditionRow(c));
      this.applyYearValues(rule.year_values || []);
      this.refreshCoverage();

      this.modalInstance.show();
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
      this.addConditionRow(null);
      this.refreshCoverageDebounced();
    }

    addConditionRow(condition) {
      const row = document.createElement("div");
      row.className = "row g-2 align-items-end mb-2";
      row.dataset.conditionRow = "1";

      const parameterOptions = PARAMETERS.map(
        (p) => `<option value="${p.code}">${escapeHtml(p.label)}</option>`,
      ).join("");
      const operatorOptions = OPERATORS.map(
        (o) => `<option value="${o.code}">${escapeHtml(o.label)}</option>`,
      ).join("");

      row.innerHTML = `
        <div class="col-md-4">
          <label class="form-label">Параметр</label>
          <select class="form-select" data-condition-parameter>
            <option value="">Выберите...</option>
            ${parameterOptions}
          </select>
        </div>
        <div class="col-md-3">
          <label class="form-label">Оператор</label>
          <select class="form-select" data-condition-operator>
            ${operatorOptions}
          </select>
        </div>
        <div class="col-md-4" data-condition-values-wrap>
          <label class="form-label">Значения</label>
          <div data-condition-values></div>
        </div>
        <div class="col-md-1">
          <button type="button" class="btn btn-outline-danger w-100" data-action="tariff-rules#removeCondition">
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

      this.renderConditionValueEditor(row, parameter, operator, values);
      this.refreshCoverageDebounced();
    }

    removeCondition(event) {
      const row = event.currentTarget.closest("[data-condition-row]");
      if (row) row.remove();
      this.refreshCoverageDebounced();
    }

    onConditionParameterChange(row) {
      const parameter = row.querySelector("[data-condition-parameter]").value;
      const operator = row.querySelector("[data-condition-operator]").value;
      this.renderConditionValueEditor(row, parameter, operator, null);
      this.refreshCoverageDebounced();
    }

    onConditionOperatorChange(row) {
      const parameter = row.querySelector("[data-condition-parameter]").value;
      const operator = row.querySelector("[data-condition-operator]").value;
      const currentValues = this.readConditionValues(row, parameter);
      this.renderConditionValueEditor(row, parameter, operator, currentValues);
      this.refreshCoverageDebounced();
    }

    async loadOptions(parameter) {
      try {
        const url = this.optionsUrlTemplateValue + "?parameter=" + encodeURIComponent(parameter);
        const { data } = await fetchJson(url, { method: "GET" });
        if (!data || !data.success) return [];
        return data.items || [];
      } catch (_e) {
        return [];
      }
    }

    renderConditionValueEditor(row, parameter, operator, values) {
      const container = row.querySelector("[data-condition-values]");
      if (!container) return;
      container.innerHTML = "";

      const paramMeta = PARAMETERS.find((p) => p.code === parameter) || null;
      const isNumeric = paramMeta && paramMeta.type === "numeric";
      const numericOp = operator === "lt" || operator === "gt";

      if (!parameter) {
        container.innerHTML = '<div class="text-muted">Сначала выберите параметр</div>';
        return;
      }

      if (isNumeric) {
        const input = document.createElement("input");
        input.type = "number";
        input.className = "form-control";
        input.placeholder = numericOp ? "Введите число" : "Введите число";
        input.dataset.conditionNumber = "1";
        input.addEventListener("input", () => this.refreshCoverageDebounced());
        if (values != null && values !== "" && !Array.isArray(values)) {
          input.value = String(values);
        }
        container.appendChild(input);
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

      const initial = Array.isArray(values)
        ? values.map((v) => String(v))
        : values != null
          ? [String(values)]
          : [];

      // В режиме редактирования важно: сначала загрузить опции (тексты),
      // затем проставить выбранные значения, иначе элементы будут "пустыми".
      this.loadOptions(parameter).then((items) => {
        const byValue = new Map((items || []).map((it) => [String(it.value), it]));
        initial.forEach((v) => {
          if (!byValue.has(String(v))) {
            ts.addOption({ value: String(v), text: String(v) });
          }
        });
        ts.addOptions(items || []);
        ts.refreshOptions(false);
        if (initial.length) ts.setValue(initial, true);
        ts.on("change", () => this.refreshCoverageDebounced());
      });
    }

    readConditionValues(row, parameter) {
      const paramMeta = PARAMETERS.find((p) => p.code === parameter) || null;
      if (paramMeta && paramMeta.type === "numeric") {
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
          const meta = PARAMETERS.find((p) => p.code === parameter) || null;
          const values = this.readConditionValues(row, parameter);
          const normalized =
            meta && meta.type === "numeric"
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
          <div class="col-6 col-md-3">
            <label class="form-label">${y}</label>
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

