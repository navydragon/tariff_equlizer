import { fetchJson } from "../lib/http.js";
import { escapeHtml } from "../lib/dom.js";
import { renderErrors } from "../lib/errors.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for scenario-edit.");
    return;
  }

  class ScenarioEditController extends Stimulus.Controller {
    static targets = [
      "form",
      "name",
      "description",
      "startYear",
      "endYear",
      "yearsError",
      "routeSetSelect",
      "rebuildStatus",
      "recomputeBtn",
    ];

    static values = {
      scenarioId: Number,
      updateUrl: String,
      recomputeUrl: String,
      routeSetListUrl: String,
      routeSetsPreloaded: Boolean,
      tabs: Array,
    };

    connect() {
      this.initTabs();
      this._autosaveTimer = null;
      this._autosaveSeq = 0;
      if (!this.routeSetsPreloadedValue) {
        this.loadRouteSets();
      }
    }

    disconnect() {
      if (this._autosaveTimer) {
        clearTimeout(this._autosaveTimer);
        this._autosaveTimer = null;
      }
      if (this.onShownTab) {
        this.element
          .querySelectorAll('[data-bs-toggle="tab"]')
          .forEach((link) => link.removeEventListener("shown.bs.tab", this.onShownTab));
      }
      if (this.onPopState) {
        window.removeEventListener("popstate", this.onPopState);
      }
    }

    // === Tabs (hash sync) ===
    initTabs() {
      this.validTabs = Array.isArray(this.tabsValue) && this.tabsValue.length
        ? this.tabsValue
        : ["tab-basic", "tab-base", "tab-tariff"];

      const initial = this.getTabFromHash();
      if (initial) this.activateTab(initial);

      this.onShownTab = (e) => {
        const href = e.target && e.target.getAttribute("href");
        if (href && href.startsWith("#")) {
          const tabId = href.slice(1);
          if (this.validTabs.includes(tabId)) {
            history.replaceState(null, "", window.location.pathname + href);
          }
        }
      };

      this.element
        .querySelectorAll('[data-bs-toggle="tab"]')
        .forEach((link) => link.addEventListener("shown.bs.tab", this.onShownTab));

      this.onPopState = () => {
        const tab = this.getTabFromHash() || "tab-basic";
        this.activateTab(tab);
      };
      window.addEventListener("popstate", this.onPopState);
    }

    getTabFromHash() {
      const hash = window.location.hash.slice(1);
      return this.validTabs.includes(hash) ? hash : null;
    }

    activateTab(tabId) {
      const triggerEl = document.querySelector("#" + tabId + "-tab");
      if (triggerEl && typeof bootstrap !== "undefined" && bootstrap.Tab) {
        new bootstrap.Tab(triggerEl).show();
      }
    }

    // === RouteSet select ===
    async loadRouteSets() {
      if (!this.hasRouteSetSelectTarget) return;
      const url = this.routeSetListUrlValue;
      if (!url) return;

      const { data } = await fetchJson(
        url + "?page=1&page_size=1000&include_routes_count=0",
        {
        method: "GET",
      });

      if (!data || !data.success) {
        this.routeSetSelectTarget.innerHTML =
          '<option value="">Ошибка загрузки</option>';
        return;
      }

      const items = data.items || [];
      if (!items.length) {
        this.routeSetSelectTarget.innerHTML =
          '<option value="">Нет наборов маршрутов</option>';
        return;
      }

      const currentIdAttr =
        this.routeSetSelectTarget.dataset.scenarioEditCurrentRouteSetIdValue;
      const currentId = currentIdAttr ? parseInt(currentIdAttr, 10) : null;

      this.routeSetSelectTarget.innerHTML = items
        .map(
          (it) =>
            `<option value="${it.id}">${escapeHtml(it.code || "")} — ${escapeHtml(
              it.name || "",
            )}</option>`,
        )
        .join("");

      if (currentId) {
        this.routeSetSelectTarget.value = String(currentId);
      }
    }

    collectExportPriceMode() {
      const checked = this.element.querySelector(
        'input.btn-check[name="export_price_mode"]:checked',
      );
      return checked ? checked.value : "fixed";
    }

    collectConsiderEnterpriseLoad() {
      const checkbox = this.element.querySelector(
        "#editScenarioConsiderEnterpriseLoad",
      );
      return checkbox ? !!checkbox.checked : true;
    }

    collectConsiderTurnoverChanges() {
      const checkbox = this.element.querySelector(
        "#editScenarioConsiderTurnoverChanges",
      );
      return checkbox ? !!checkbox.checked : false;
    }

    collectConsiderDemandElasticity() {
      const checkbox = this.element.querySelector(
        "#editScenarioConsiderDemandElasticity",
      );
      return checkbox ? !!checkbox.checked : false;
    }

    collectIgnoreOwnAxlesCargo() {
      const checkbox = this.element.querySelector(
        "#editScenarioIgnoreOwnAxlesCargo",
      );
      return checkbox ? !!checkbox.checked : false;
    }

    collectRetentionCoefficientMode() {
      const checked = this.element.querySelector(
        'input.btn-check[name="retention_coefficient_mode"]:checked',
      );
      return checked ? checked.value : "combined";
    }

    collectPriceChangeSettings() {
      const settings = {};
      const inputs = this.element.querySelectorAll(
        'input.btn-check[name^="price_change__"]',
      );
      inputs.forEach((input) => {
        if (!input.checked) return;
        const name = input.getAttribute("name") || "";
        const prefix = "price_change__";
        if (!name.startsWith(prefix)) return;
        const parameter = name.slice(prefix.length);
        settings[parameter] = input.value;
      });
      return settings;
    }

    // === Autosave ===
    autosave(event) {
      if (event && typeof event.preventDefault === "function") {
        event.preventDefault();
      }

      if (this._autosaveTimer) {
        clearTimeout(this._autosaveTimer);
      }

      this._autosaveTimer = setTimeout(() => {
        void this._autosaveNow();
      }, 400);
    }

    async _autosaveNow() {
      const errorsContainer = document.getElementById("editScenarioErrors");

      const { ok, errors, startYear, endYear } = this._validateYears();
      if (!ok) {
        this._setYearsError(errors.join(" "));
        return;
      }

      this._setYearsError("");
      if (errorsContainer) {
        errorsContainer.innerHTML = "";
      }

      const payload = this._buildPayload({ startYear, endYear });
      const url = this.updateUrlValue;
      if (!url) return;

      const seq = (this._autosaveSeq += 1);
      const { data } = await fetchJson(url, { method: "POST", body: payload });
      if (seq !== this._autosaveSeq) {
        return;
      }

      if (!data || !data.success) {
        const errs =
          (data && (data.errors || (data.error ? [data.error] : null))) || [
            "Ошибка при сохранении сценария",
          ];
        if (errorsContainer) {
          errorsContainer.innerHTML = "";
          const div = document.createElement("div");
          div.className = "alert alert-danger";
          errorsContainer.appendChild(div);
          renderErrors(div, errs);
          errorsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        this.showToast("error", errs.join("<br>"));
      }
    }

    _validateYears() {
      const errors = [];
      const startRaw = this.hasStartYearTarget ? String(this.startYearTarget.value || "").trim() : "";
      const endRaw = this.hasEndYearTarget ? String(this.endYearTarget.value || "").trim() : "";

      if (!/^\d{4}$/.test(startRaw)) {
        errors.push("Год начала должен быть в формате ГГГГ");
      }
      if (!/^\d{4}$/.test(endRaw)) {
        errors.push("Год окончания должен быть в формате ГГГГ");
      }

      const startYear = /^\d{4}$/.test(startRaw) ? parseInt(startRaw, 10) : null;
      const endYear = /^\d{4}$/.test(endRaw) ? parseInt(endRaw, 10) : null;

      if (startYear != null && (startYear < 2000 || startYear > 2100)) {
        errors.push("Год начала должен быть в пределах 2000-2100");
      }
      if (endYear != null && (endYear < 2000 || endYear > 2100)) {
        errors.push("Год окончания должен быть в пределах 2000-2100");
      }
      if (startYear != null && endYear != null && startYear >= endYear) {
        errors.push("Год начала должен быть меньше года окончания");
      }

      if (errors.length) {
        return { ok: false, errors, startYear: null, endYear: null };
      }
      return { ok: true, errors: [], startYear, endYear };
    }

    _setYearsError(message) {
      if (!this.hasYearsErrorTarget) return;
      const text = String(message || "").trim();
      if (!text) {
        this.yearsErrorTarget.textContent = "";
        this.yearsErrorTarget.classList.add("d-none");
        return;
      }
      this.yearsErrorTarget.textContent = text;
      this.yearsErrorTarget.classList.remove("d-none");
    }

    _buildPayload({ startYear, endYear }) {
      const routeSetId = this.hasRouteSetSelectTarget
        ? parseInt(this.routeSetSelectTarget.value || "0", 10)
        : 0;

      return {
        name: this.hasNameTarget ? this.nameTarget.value : "",
        description: this.hasDescriptionTarget ? this.descriptionTarget.value : "",
        // Важно: годы всегда уходят парой.
        start_year: startYear,
        end_year: endYear,
        route_set_id: routeSetId || null,
        price_change_settings: this.collectPriceChangeSettings(),
        export_price_mode: this.collectExportPriceMode(),
        consider_turnover_changes: this.collectConsiderTurnoverChanges(),
        consider_demand_elasticity: this.collectConsiderDemandElasticity(),
        consider_enterprise_load: this.collectConsiderEnterpriseLoad(),
        ignore_own_axles_cargo: this.collectIgnoreOwnAxlesCargo(),
        retention_coefficient_mode: this.collectRetentionCoefficientMode(),
      };
    }

    async recompute() {
      if (!this.hasRecomputeUrlValue) return;

      this._setRecomputeBusy(true);

      const { data } = await fetchJson(this.recomputeUrlValue, {
        method: "POST",
        body: {},
      });

      if (!data || !data.success) {
        const errs = (data && (data.errors || (data.error ? [data.error] : null))) || [
          "Не удалось запустить пересчёт",
        ];
        this._showRebuildStatus(errs.join(", "), "danger");
        this._setRecomputeBusy(false);
        return;
      }

      if (!data.rebuild?.started) {
        this._hideRebuildStatus();
        this._setRecomputeBusy(false);
        this.showToast("error", "Пересчёт не был запущен");
        return;
      }

      this._notifyScenarioRecalculated();
      this._requestCloseModal();
    }

    _setRecomputeBusy(isBusy) {
      if (this.hasRecomputeBtnTarget) {
        this.recomputeBtnTarget.disabled = isBusy;
      }
    }

    _hideRebuildStatus() {
      if (!this.hasRebuildStatusTarget) return;
      this.rebuildStatusTarget.classList.add("d-none");
      this.rebuildStatusTarget.innerHTML = "";
    }

    _showRebuildStatus(message, variant = "info") {
      if (!this.hasRebuildStatusTarget) return;
      const alertClass =
        variant === "success"
          ? "alert-success"
          : variant === "danger"
            ? "alert-danger"
            : "alert-info";
      this.rebuildStatusTarget.classList.remove("d-none");
      this.rebuildStatusTarget.innerHTML = `
        <div class="alert ${alertClass} py-2 px-3 mb-0" role="status">
          ${variant === "danger" ? "" : '<span class="spinner-border spinner-border-sm text-primary me-2" role="status"></span>'}
          ${escapeHtml(message)}
        </div>
      `;
    }

    _notifyScenarioRecalculated() {
      if (!this.hasScenarioIdValue) return;
      const detail = { scenarioId: this.scenarioIdValue };
      document.dispatchEvent(
        new CustomEvent("scenario-recalculated", { detail }),
      );
      if (window.parent !== window) {
        window.parent.postMessage(
          { type: "scenario-recalculated", scenarioId: this.scenarioIdValue },
          window.location.origin,
        );
      }
    }

    _requestCloseModal() {
      if (window.parent !== window) {
        window.parent.postMessage(
          { type: "close-scenario-edit-modal" },
          window.location.origin,
        );
      }
    }

    showToast(type, message) {
      let toastElement;
      if (type === "success") {
        toastElement = document.getElementById("toastSuccess");
      } else {
        toastElement = document.getElementById("toastError");
        const toastBody = document.getElementById("toastErrorBody");
        if (toastBody) toastBody.innerHTML = message;
      }

      if (toastElement && typeof bootstrap !== "undefined") {
        const toast = new bootstrap.Toast(toastElement, {
          autohide: true,
          delay: 5000,
        });
        toast.show();
      }
    }
  }

  application.register("scenario-edit", ScenarioEditController);
})();
