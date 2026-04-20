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
      "routeSetSelect",
    ];

    static values = {
      scenarioId: Number,
      updateUrl: String,
      routeSetListUrl: String,
      tabs: Array,
    };

    connect() {
      this.initTabs();
      this.loadRouteSets();
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

    disconnect() {
      if (this.onShownTab) {
        this.element
          .querySelectorAll('[data-bs-toggle="tab"]')
          .forEach((link) => link.removeEventListener("shown.bs.tab", this.onShownTab));
      }
      if (this.onPopState) {
        window.removeEventListener("popstate", this.onPopState);
      }
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

      const { data } = await fetchJson(url + "?page=1&page_size=1000", {
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

    // === Form submit ===
    async submit(event) {
      event.preventDefault();

      const errorsContainer = document.getElementById("editScenarioErrors");
      if (errorsContainer) errorsContainer.innerHTML = "";

      const routeSetId = this.hasRouteSetSelectTarget
        ? parseInt(this.routeSetSelectTarget.value || "0", 10)
        : 0;

      const payload = {
        name: this.hasNameTarget ? this.nameTarget.value : "",
        description: this.hasDescriptionTarget ? this.descriptionTarget.value : "",
        start_year: this.hasStartYearTarget
          ? parseInt(this.startYearTarget.value || "0", 10)
          : null,
        end_year: this.hasEndYearTarget
          ? parseInt(this.endYearTarget.value || "0", 10)
          : null,
        route_set_id: routeSetId || null,
      };

      const url = this.updateUrlValue;
      const { data } = await fetchJson(url, { method: "POST", body: payload });

      if (!data || !data.success) {
        const errs = (data && (data.errors || (data.error ? [data.error] : null))) || [
          "Ошибка при сохранении сценария",
        ];
        if (errorsContainer) {
          const div = document.createElement("div");
          div.className = "alert alert-danger";
          errorsContainer.appendChild(div);
          renderErrors(div, errs);
          errorsContainer.scrollIntoView({ behavior: "smooth", block: "start" });
        }
        this.showToast("error", errs.join("<br>"));
        return;
      }

      this.showToast("success", "Сценарий успешно обновлен");
    }

    showToast(type, message) {
      let toastElement;
      if (type === "success") {
        toastElement = document.getElementById("toastSuccess");
        const timeElement = document.getElementById("toastSuccessTime");
        if (timeElement) {
          const now = new Date();
          const dateStr = now.toLocaleDateString("ru-RU", {
            day: "2-digit",
            month: "2-digit",
            year: "numeric",
          });
          const timeStr = now.toLocaleTimeString("ru-RU", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
          timeElement.textContent = dateStr + " " + timeStr;
        }
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

