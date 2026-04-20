import { fetchJson } from "../lib/http.js";
import { escapeHtml, setVisible } from "../lib/dom.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error(
      "Stimulus application is not initialized for scenario-drawer-route-picker.",
    );
    return;
  }

  class ScenarioDrawerRoutePickerController extends Stimulus.Controller {
    static targets = [
      "searchInput",
      "routeList",
      "routeLoading",
      "routeEmpty",
      "routeErrors",
    ];

    static values = {
      routesListUrl: String,
      pageSize: { type: Number, default: 20 },
      searchDebounceMs: { type: Number, default: 400 },
    };

    connect() {
      this.state = {
        routeSetId: null,
        searchTimeout: null,
        routesRequestInFlight: null,
      };
      this._onScenarioChanged = this._onScenarioActiveChanged.bind(this);
      document.addEventListener("scenario:active-changed", this._onScenarioChanged);
    }

    disconnect() {
      document.removeEventListener(
        "scenario:active-changed",
        this._onScenarioChanged,
      );
    }

    _onScenarioActiveChanged(event) {
      const detail = event.detail || {};
      const routeSetId = detail.routeSetId != null ? Number(detail.routeSetId) : null;
      this.state.routeSetId =
        routeSetId && !Number.isNaN(routeSetId) ? routeSetId : null;

      if (this.hasSearchInputTarget) {
        this.searchInputTarget.value = "";
      }

      if (this.state.routeSetId) {
        this._loadRoutes({ search: "", page: 1 });
      } else {
        this._clearRouteListUi();
      }
    }

    onSearchInput() {
      clearTimeout(this.state.searchTimeout);
      this.state.searchTimeout = setTimeout(() => {
        if (!this.state.routeSetId) return;
        this._loadRoutes({
          search: this.hasSearchInputTarget ? this.searchInputTarget.value : "",
          page: 1,
        });
      }, this.searchDebounceMsValue || 400);
    }

    _clearRouteListUi() {
      this._setRouteLoading(false);
      if (this.hasRouteListTarget) {
        this.routeListTarget.innerHTML = "";
      }
      setVisible(this.routeEmptyTarget, false);
      if (this.hasRouteErrorsTarget) {
        this.routeErrorsTarget.classList.add("d-none");
        this.routeErrorsTarget.textContent = "";
      }
    }

    async _loadRoutes({ search, page }) {
      if (!this.state.routeSetId) return;

      const query = new URLSearchParams();
      query.set("route_set_id", String(this.state.routeSetId));
      query.set("search", (search || "").trim());
      query.set("page", String(page || 1));
      query.set("page_size", String(this.pageSizeValue || 20));

      const url = `${this.routesListUrlValue}?${query.toString()}`;
      const requestToken = {};
      this.state.routesRequestInFlight = requestToken;

      this._setRouteLoading(true);
      if (this.hasRouteErrorsTarget) {
        this.routeErrorsTarget.classList.add("d-none");
        this.routeErrorsTarget.textContent = "";
      }

      const { data } = await fetchJson(url);
      if (this.state.routesRequestInFlight !== requestToken) return;

      if (!data || !data.success) {
        const msg =
          (data && data.errors && data.errors.join(", ")) ||
          "Ошибка загрузки маршрутов";
        if (this.hasRouteErrorsTarget) {
          this.routeErrorsTarget.classList.remove("d-none");
          this.routeErrorsTarget.textContent = msg;
        }
        this._setRouteLoading(false);
        return;
      }

      const items = data.items || [];
      this.routeListTarget.innerHTML = "";

      setVisible(this.routeEmptyTarget, items.length === 0);

      for (const route of items) {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "list-group-item list-group-item-action text-start";
        const cargo = route.cargo_name || "";
        const origin = route.origin_station_name || "";
        const destination = route.destination_station_name || "";
        const msgType = route.message_type_name || "";
        const routeCode = route.route_code || "";
        el.innerHTML = `
          <div class="d-flex w-100 justify-content-between gap-2">
            <div>
              <div class="fw-medium">${escapeHtml(routeCode)}</div>
              <div class="text-muted small">${escapeHtml(cargo)}</div>
              <div class="text-muted small">${escapeHtml(origin)} → ${escapeHtml(destination)}</div>
            </div>
            <div class="text-muted small text-end">${escapeHtml(msgType)}</div>
          </div>
        `;
        el.addEventListener("click", () => this._selectRoute(route));
        this.routeListTarget.appendChild(el);
      }

      this._setRouteLoading(false);
    }

    _setRouteLoading(loading) {
      if (!this.hasRouteLoadingTarget) return;
      setVisible(this.routeLoadingTarget, !!loading);
    }

    _selectRoute(route) {
      this._renderDashboardSelectedRoute(route);
      this._hideScenariosDrawer();
    }

    _renderDashboardSelectedRoute(route) {
      const ph = document.getElementById("dashboardRoutePlaceholder");
      const card = document.getElementById("dashboardSelectedRouteCard");
      const codeEl = document.getElementById("dashboardRouteCode");
      const cargoEl = document.getElementById("dashboardRouteCargo");
      const originEl = document.getElementById("dashboardRouteOrigin");
      const destEl = document.getElementById("dashboardRouteDestination");
      const msgEl = document.getElementById("dashboardRouteMessageType");
      if (!ph || !card || !codeEl || !cargoEl || !originEl || !destEl || !msgEl)
        return;

      ph.style.display = "none";
      card.style.display = "";

      codeEl.textContent = route.route_code || "";
      cargoEl.textContent = route.cargo_name || "";
      originEl.textContent = route.origin_station_name || "";
      destEl.textContent = route.destination_station_name || "";
      const msgType = route.message_type_name || "";
      msgEl.textContent = msgType ? `Вид сообщения: ${msgType}` : "";
    }

    _hideScenariosDrawer() {
      const el = document.getElementById("scenariosDrawer");
      if (!el || typeof bootstrap === "undefined") return;
      const inst =
        bootstrap.Offcanvas.getInstance(el) ||
        bootstrap.Offcanvas.getOrCreateInstance(el);
      if (!inst) return;

      // При программном закрытии offcanvas иногда остаются backdrop/классы Bootstrap,
      // из-за чего следующий открывшийся offcanvas может мгновенно закрываться.
      // Чистим состояние только после события скрытия.
      const cleanupBackdrops = () => {
        document
          .querySelectorAll(".offcanvas-backdrop, .modal-backdrop")
          .forEach((b) => b.remove());
        document.body.classList.remove("modal-open");
      };

      el.addEventListener("hidden.bs.offcanvas", cleanupBackdrops, {
        once: true,
      });

      // Стараемся закрывать "штатно" через data-bs-dismiss, чтобы Bootstrap
      // корректно отработал свой backdrop/body state.
      const closeBtn = el.querySelector('[data-bs-dismiss="offcanvas"]');
      if (closeBtn) {
        closeBtn.click();
      } else {
        inst.hide();
      }

      // fallback: если hidden-событие не сработало по какой-то причине
      // (или backdrop не успел обновиться) - чистим чуть позже.
      setTimeout(cleanupBackdrops, 400);
    }
  }

  application.register("scenario-drawer-route-picker", ScenarioDrawerRoutePickerController);
})();
