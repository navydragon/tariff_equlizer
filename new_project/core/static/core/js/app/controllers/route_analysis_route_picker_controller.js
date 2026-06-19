import { fetchJson } from "../lib/http.js";
import { escapeHtml, setVisible } from "../lib/dom.js";
import { persistActiveScenario } from "../lib/scenario_active.js";

(function () {
  // eslint-disable-next-line no-console
  console.info("[route-analysis] controller module loaded");

  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error(
      "Stimulus application is not initialized for route-analysis-route-picker.",
    );
    return;
  }

  class RouteAnalysisRoutePickerController extends Stimulus.Controller {
    static CASCADE_SELECT_IDS = {
      cargoGroupFilterSelect: "routeAnalysisCargoGroupFilter",
      cargoFilterSelect: "routeAnalysisCargoFilter",
      transportTypeFilterSelect: "routeAnalysisTransportTypeFilter",
      holdingFilterCargoSelect: "routeAnalysisHoldingFilterCargo",
      holdingFilterHoldingSelect: "routeAnalysisHoldingFilterHolding",
      transportTypeFilterHoldingSelect: "routeAnalysisTransportTypeFilterHolding",
      cargoFilterHoldingSelect: "routeAnalysisCargoFilterHolding",
    };

    static targets = [
      "scenarioSelect",
      "searchInput",
      "filtersCollapse",
      "searchCollapse",
      "pickerModeCargo",
      "pickerModeHolding",
      "cargoFirstFilters",
      "holdingFirstFilters",
      "cargoGroupFilterSelect",
      "cargoFilterSelect",
      "transportTypeFilterSelect",
      "holdingFilterCargoSelect",
      "holdingFilterHoldingSelect",
      "transportTypeFilterHoldingSelect",
      "cargoFilterHoldingSelect",
      "routeList",
      "loading",
      "empty",
      "errors",
      "confirmButton",
      "routesTiming",
      "diagramTypeSelect",
      "diagramPlaceholder",
      "equalizerTypeSelect",
      "equalizerPanel",
      "equalizerEmpty",
      "equalizerControls",
      "equalizerUnitHint",
    ];

    static values = {
      scenariosUrl: String,
      routesUrl: String,
      pickerOptionsUrl: String,
      routeAnalysisUrl: String,
      activeScenarioId: String,
      pageSize: { type: Number, default: 20 },
      searchDebounceMs: { type: Number, default: 400 },
    };

    connect() {
      // eslint-disable-next-line no-console
      console.info("[route-analysis] controller connected", this.element);
      const dbg = document.getElementById("routeAnalysisDebug");
      if (dbg) {
        dbg.textContent = "route-analysis-route-picker: connected";
      }

      this.state = {
        modal: null,
        modalEl: null,
        boundSearchHandler: null,
        boundConfirmHandler: null,
        boundScrollHandler: null,
        boundFiltersToggleHandler: null,
        boundSearchToggleHandler: null,
        searchTimeout: null,
        cascadeFilterTimeout: null,
        routesRequestInFlight: null,
        routesPage: 1,
        routesHasNext: false,
        routesIsLoadingMore: false,
        routesLastSearch: "",
        routesLastCascade: {
          cargoGroup: "",
          cargo: "",
          transportType: "",
          holding: "",
        },
        pickerMode: "cargo_first",
        cascade: {
          cargoGroup: "",
          cargo: "",
          transportType: "",
          holding: "",
        },
        cascadeTomSelects: {},
        cascadeTomSelectInitialized: false,
        routesLastCount: 0,
        routesLastElapsedMs: null,
        scenarioById: new Map(),
        selectedScenario: null,
        selectedScenarioId: null,
        selectedRouteSetId: null,
        pendingSelectedRoute: null,
        selectedRoute: null,
        trendsChart: null,
        routeAnalysisCache: new Map(),
        activeCalculateData: null,
        equalizerBaseline: null,
        equalizerOverrides: {},
        equalizerDebounceTimer: null,
        equalizerRecalcInFlight: false,
      };

      this.state.modalEl = document.getElementById("routeAnalysisRouteModal");
      if (this.state.modalEl && typeof bootstrap !== "undefined") {
        this.state.modal =
          bootstrap.Modal.getInstance(this.state.modalEl) ||
          bootstrap.Modal.getOrCreateInstance(this.state.modalEl);
      }
      this.state.boundSearchHandler = this.onSearchInput.bind(this);
      this.state.pickerMode = this._getPickerMode();

      this._bindFiltersCollapseListener();
      this._bindSearchCollapseListener();
      this._ensureModalHandlers();
      this._syncPickerModeVisibility();
      this._resetUi();
      this._renderRouteDetails(null);
      this._updateEqualizerVisibility(false);

      // Загружаем сценарии сразу при открытии страницы, чтобы верхний select
      // не был пустым и не зависел от открытия модалки.
      this._renderScenarioLoadingPlaceholder();
      this._initScenariosOnPage();

      // Инициализируем заглушку диаграмм.
      this._renderDiagram();
    }

    disconnect() {
      clearTimeout(this.state.searchTimeout);
      clearTimeout(this.state.cascadeFilterTimeout);
      this._destroyCascadeTomSelects();
    }

    onFiltersShown() {
      this._ensureCascadeTomSelects();
    }

    toggleFilters(event) {
      if (event && typeof event.preventDefault === "function") {
        event.preventDefault();
      }
      const collapseEl = document.getElementById("routeAnalysisFiltersCollapse");
      if (!collapseEl || typeof bootstrap === "undefined") return;
      bootstrap.Collapse.getOrCreateInstance(collapseEl).toggle();
    }

    toggleSearch(event) {
      if (event && typeof event.preventDefault === "function") {
        event.preventDefault();
      }
      const collapseEl = document.getElementById("routeAnalysisSearchCollapse");
      if (!collapseEl || typeof bootstrap === "undefined") return;
      bootstrap.Collapse.getOrCreateInstance(collapseEl).toggle();
    }

    onPickerModeChange() {
      const mode = this._getPickerMode();
      if (mode === this.state.pickerMode) return;
      this.state.pickerMode = mode;
      this._syncPickerModeVisibility();
      this._resetCascadeFilters();
      this._destroyCascadeTomSelects();
      this._ensureCascadeTomSelects();
      this._resetRouteListOnly();
      this._resetRoutesPagination();
    }

    _syncPickerModeVisibility() {
      const cargoFirst = this._getPickerMode() === "cargo_first";
      if (this.hasCargoFirstFiltersTarget) {
        this.cargoFirstFiltersTarget.style.display = cargoFirst ? "" : "none";
      }
      if (this.hasHoldingFirstFiltersTarget) {
        this.holdingFirstFiltersTarget.style.display = cargoFirst ? "none" : "";
      }
    }

    _getPickerMode() {
      if (
        this.hasPickerModeHoldingTarget &&
        this.pickerModeHoldingTarget.checked
      ) {
        return "holding_first";
      }
      return "cargo_first";
    }

    _getActiveCascadeChain() {
      if (this._getPickerMode() === "holding_first") {
        return [
          {
            key: "holding",
            targetName: "holdingFilterHoldingSelect",
            dimension: "holding",
          },
          {
            key: "transportType",
            targetName: "transportTypeFilterHoldingSelect",
            dimension: "transport_type",
          },
          {
            key: "cargo",
            targetName: "cargoFilterHoldingSelect",
            dimension: "cargo",
          },
        ];
      }
      return [
        {
          key: "cargoGroup",
          targetName: "cargoGroupFilterSelect",
          dimension: "cargo_group",
        },
        {
          key: "cargo",
          targetName: "cargoFilterSelect",
          dimension: "cargo",
        },
        {
          key: "transportType",
          targetName: "transportTypeFilterSelect",
          dimension: "transport_type",
        },
        {
          key: "holding",
          targetName: "holdingFilterCargoSelect",
          dimension: "holding",
        },
      ];
    }

    onCascadeFilterChange() {
      clearTimeout(this.state.cascadeFilterTimeout);
      this.state.routesPage = 1;
      this.state.routesHasNext = false;
      this.state.cascadeFilterTimeout = setTimeout(() => {
        this._maybeLoadRoutesFromFilters();
      }, this.searchDebounceMsValue || 400);
    }

    onDiagramTypeChange() {
      this._renderDiagram();
    }

    _bindFiltersCollapseListener() {
      const collapseEl = document.getElementById("routeAnalysisFiltersCollapse");
      if (!collapseEl || collapseEl.dataset.holdingCollapseBound) return;
      collapseEl.dataset.holdingCollapseBound = "1";
      collapseEl.addEventListener("shown.bs.collapse", () => {
        this._ensureCascadeTomSelects();
        this._syncFiltersToggleAria(true);
      });
      collapseEl.addEventListener("hidden.bs.collapse", () => {
        this._syncFiltersToggleAria(false);
      });
    }

    _syncFiltersToggleAria(expanded) {
      const btn = document.getElementById("routeAnalysisFiltersToggle");
      if (btn) {
        btn.setAttribute("aria-expanded", expanded ? "true" : "false");
      }
    }

    _bindSearchCollapseListener() {
      const collapseEl = document.getElementById("routeAnalysisSearchCollapse");
      if (!collapseEl || collapseEl.dataset.searchCollapseBound) return;
      collapseEl.dataset.searchCollapseBound = "1";
      collapseEl.addEventListener("shown.bs.collapse", () => {
        this._syncSearchToggleAria(true);
        if (this.hasSearchInputTarget) {
          this.searchInputTarget.focus();
        }
      });
      collapseEl.addEventListener("hidden.bs.collapse", () => {
        this._syncSearchToggleAria(false);
      });
    }

    _syncSearchToggleAria(expanded) {
      const btn = document.getElementById("routeAnalysisSearchToggle");
      if (btn) {
        btn.setAttribute("aria-expanded", expanded ? "true" : "false");
      }
    }

    async openModal() {
      this._resetUi();
      this._syncPickerModeVisibility();
      if (this.state.modal) {
        this.state.modal.show();
      }
      this._ensureModalHandlers();
      this._ensureCascadeTomSelects();
      const input = this._getSearchInputEl();
      if (input) input.focus();
    }

    onScenarioChange() {
      const raw = this.hasScenarioSelectTarget
        ? this.scenarioSelectTarget.value
        : "";
      const scenarioId = raw ? Number(raw) : null;
      this.state.routeAnalysisCache.clear();
      this._destroyCascadeTomSelects();
      this._setScenario(scenarioId);
      this._persistActiveScenario(scenarioId);
      this._resetRouteSearch();
      this._renderRouteDetails(null);
      this.state.selectedRoute = null;
      this._resetEqualizer();
      this._renderDiagram();
    }

    onSearchInput() {
      clearTimeout(this.state.searchTimeout);
      this.state.routesPage = 1;
      this.state.routesHasNext = false;
      // eslint-disable-next-line no-console
      console.info("[route-analysis] onSearchInput", {
        selectedScenarioId: this.state.selectedScenarioId,
        selectedRouteSetId: this.state.selectedRouteSetId,
        query: this._getSearchInputEl() ? this._getSearchInputEl().value : "",
      });
      this.state.searchTimeout = setTimeout(() => {
        this._maybeLoadRoutesFromFilters();
      }, this.searchDebounceMsValue || 400);
    }

    async confirmSelection() {
      // eslint-disable-next-line no-console
      console.info("[route-analysis] confirmSelection", {
        hasPending: !!this.state.pendingSelectedRoute,
      });
      if (!this.state.pendingSelectedRoute) return;
      this.state.selectedRoute = this.state.pendingSelectedRoute;
      this._renderRouteDetails(this.state.selectedRoute);
      if (this.state.modal) {
        this.state.modal.hide();
      }

      this.state.routeAnalysisCache.clear();
      this.state.equalizerOverrides = {};
      await this._loadEqualizerBaseline();
      this._renderDiagram();
    }

    onEqualizerTypeChange() {
      this._renderEqualizerPanel();
    }

    async _loadScenarios() {
      if (!this.scenariosUrlValue) return;

      this._showErrors([]);
      this._renderScenarioLoadingPlaceholder();
      const { data } = await fetchJson(this.scenariosUrlValue);
      if (!data || !data.success) {
        this._showErrors((data && data.errors) || ["Ошибка загрузки сценариев"]);
        return;
      }

      const scenarios = data.scenarios || [];
      this.state.scenarioById = new Map(
        scenarios.map((s) => [Number(s.id), s]),
      );

      if (this.hasScenarioSelectTarget) {
        this.scenarioSelectTarget.innerHTML = "";
        if (scenarios.length === 0) {
          const opt = document.createElement("option");
          opt.value = "";
          opt.textContent = "Нет доступных сценариев";
          this.scenarioSelectTarget.appendChild(opt);
          this._setScenario(null);
          return;
        }
        for (const s of scenarios) {
          const opt = document.createElement("option");
          opt.value = String(s.id);
          opt.textContent = s.name || `Сценарий #${s.id}`;
          this.scenarioSelectTarget.appendChild(opt);
        }
      }
    }

    _selectDefaultScenario() {
      const activeId = this._parseActiveScenarioId();
      const fallbackId = this._firstScenarioId();
      const scenarioId =
        activeId && this.state.scenarioById.has(activeId) ? activeId : fallbackId;

      if (this.hasScenarioSelectTarget && scenarioId != null) {
        this.scenarioSelectTarget.value = String(scenarioId);
      }
      this._setScenario(scenarioId);
      this._resetRouteSearch();
    }

    async _initScenariosOnPage() {
      try {
        await this._loadScenarios();
        this._selectDefaultScenario();
        this._renderDiagram();
      } catch (e) {
        this._showErrors(["Ошибка инициализации сценариев (см. консоль)"]);
        // eslint-disable-next-line no-console
        console.error("route-analysis-route-picker init failed", e);
      }
    }

    _renderScenarioLoadingPlaceholder() {
      if (!this.hasScenarioSelectTarget) return;
      if (this.scenarioSelectTarget.options.length > 0) return;
      const opt = document.createElement("option");
      opt.value = "";
      opt.textContent = "Загрузка…";
      this.scenarioSelectTarget.appendChild(opt);
    }

    _parseActiveScenarioId() {
      const raw = (this.activeScenarioIdValue || "").trim();
      if (!raw) return null;
      const n = Number(raw);
      return Number.isFinite(n) ? n : null;
    }

    _firstScenarioId() {
      for (const id of this.state.scenarioById.keys()) {
        return id;
      }
      return null;
    }

    _setScenario(scenarioId) {
      this.state.selectedScenarioId = scenarioId;
      this.state.pendingSelectedRoute = null;
      this._setConfirmEnabled(false);

      const s =
        scenarioId != null ? this.state.scenarioById.get(scenarioId) : null;
      this.state.selectedScenario = s || null;
      const routeSetId = s && s.route_set_id != null ? Number(s.route_set_id) : null;
      this.state.selectedRouteSetId =
        routeSetId && !Number.isNaN(routeSetId) ? routeSetId : null;
    }

    _persistActiveScenario(scenarioId) {
      if (!scenarioId) return;

      const scenario = this.state.scenarioById.get(scenarioId);
      const activeId = this._parseActiveScenarioId();
      if (activeId === scenarioId) return;

      void persistActiveScenario(scenarioId, {
        routeSetId: scenario?.route_set_id,
        onError: (errors) => {
          this._showErrors(errors || ["Не удалось сохранить активный сценарий"]);
        },
      }).then((ok) => {
        if (ok) {
          this.activeScenarioIdValue = String(scenarioId);
        }
      });
    }

    _resetRouteSearch() {
      if (this.hasSearchInputTarget) {
        this.searchInputTarget.value = "";
      }
      this._resetCascadeFilters();
      this._resetRouteListOnly();
      this._resetRoutesPagination();
    }

    _resetRouteListOnly() {
      if (this.hasRouteListTarget) {
        this.routeListTarget.innerHTML = "";
      }
      if (this.hasEmptyTarget) setVisible(this.emptyTarget, false);
      this._setLoading(false);
      this._updateRoutesTiming(null, null);
    }

    _resetRoutesPagination() {
      this.state.routesPage = 1;
      this.state.routesHasNext = false;
      this.state.routesIsLoadingMore = false;
      this.state.routesLastSearch = "";
      this.state.routesLastCascade = {
        cargoGroup: "",
        cargo: "",
        transportType: "",
        holding: "",
      };
      this.state.routesLastCount = 0;
      this.state.routesLastElapsedMs = null;
      this._removeLoadMoreSentinel();
    }

    _getCascadeValues() {
      return { ...this.state.cascade };
    }

    _emptyCascade() {
      return {
        cargoGroup: "",
        cargo: "",
        transportType: "",
        holding: "",
      };
    }

    _isCascadeComplete(cascade = this.state.cascade) {
      if (this._getPickerMode() === "holding_first") {
        return Boolean(cascade.holding && cascade.transportType && cascade.cargo);
      }
      return Boolean(
        cascade.cargoGroup &&
          cascade.cargo &&
          cascade.transportType &&
          cascade.holding,
      );
    }

    _shouldLoadRoutes(search, cascade) {
      const normalizedSearch = (search || "").trim();
      if (normalizedSearch) return true;
      return this._isCascadeComplete(cascade);
    }

    _maybeLoadRoutesFromFilters() {
      const search = this._getSearchInputEl()
        ? this._getSearchInputEl().value
        : "";
      const cascade = this._getCascadeValues();
      if (!this._shouldLoadRoutes(search, cascade)) {
        this._resetRouteListOnly();
        return;
      }
      this._loadRoutes({
        search,
        cascade,
        page: 1,
        append: false,
      });
    }

    async _loadRoutes({ search, cascade, page, append = false }) {
      if (!this.routesUrlValue) return;
      if (!this.state.selectedRouteSetId) {
        this._showErrors(["У выбранного сценария не задан набор маршрутов"]);
        // eslint-disable-next-line no-console
        console.warn("[route-analysis] skip routes fetch: route_set_id is empty");
        return;
      }

      const normalizedSearch = (search || "").trim();
      const normalizedCascade = cascade || this._emptyCascade();
      if (!this._shouldLoadRoutes(normalizedSearch, normalizedCascade)) {
        return;
      }

      // eslint-disable-next-line no-console
      console.info("[route-analysis] fetching routes", {
        routeSetId: this.state.selectedRouteSetId,
        search: normalizedSearch,
        cascade: normalizedCascade,
        page: page || 1,
      });

      const query = new URLSearchParams();
      query.set("route_set_id", String(this.state.selectedRouteSetId));
      query.set("search", normalizedSearch);
      if (normalizedCascade.cargoGroup) {
        query.set("cargo_group_name", normalizedCascade.cargoGroup);
      }
      if (normalizedCascade.cargo) {
        query.set("cargo_code", normalizedCascade.cargo);
      }
      if (normalizedCascade.transportType) {
        query.set("message_type_name", normalizedCascade.transportType);
      }
      if (normalizedCascade.holding) {
        query.set("holding", normalizedCascade.holding);
      }
      query.set("page", String(page || 1));
      query.set("page_size", String(this.pageSizeValue || 20));
      query.set("include_total", "0");
      query.set("economics_filled", "1");

      const url = `${this.routesUrlValue}?${query.toString()}`;
      const requestToken = {};
      this.state.routesRequestInFlight = requestToken;

      this._showErrors([]);
      if (append) {
        this.state.routesIsLoadingMore = true;
        this._showLoadMoreSentinel();
      } else {
        const listEl = this._getRouteListEl();
        if (listEl) listEl.innerHTML = "";
        this._setLoading(true);
      }

      const { data } = await fetchJson(url);
      if (this.state.routesRequestInFlight !== requestToken) return;

      if (!data || !data.success) {
        this._showErrors((data && data.errors) || ["Ошибка загрузки маршрутов"]);
        if (append) {
          this.state.routesIsLoadingMore = false;
          this._removeLoadMoreSentinel();
        } else {
          this._setLoading(false);
        }
        return;
      }

      const items = data.items || [];
      this.state.routesLastSearch = normalizedSearch;
      this.state.routesLastCascade = { ...normalizedCascade };
      this.state.routesPage = page || 1;
      this.state.routesHasNext = Boolean(data.has_next);
      if (!append) {
        this.state.routesLastCount = items.length;
        this.state.routesLastElapsedMs =
          data.elapsed_ms != null ? data.elapsed_ms : null;
        this._updateRoutesTiming(this.state.routesLastCount, data.elapsed_ms);
      }
      this._renderRouteList(items, { append });
      if (append) {
        this.state.routesIsLoadingMore = false;
        this._removeLoadMoreSentinel();
      } else {
        this._setLoading(false);
      }
    }

    _renderRouteList(items, { append = false } = {}) {
      const listEl = this._getRouteListEl();
      if (!listEl) return;
      if (!append) {
        listEl.innerHTML = "";
        this.state.pendingSelectedRoute = null;
        this._setConfirmEnabled(false);
      }

      const emptyEl = this._getEmptyEl();
      if (emptyEl) {
        setVisible(emptyEl, !append && items.length === 0);
      }

      const badge = (text, icon, variant) => {
        if (!text) return "";
        const v = variant || "azure";
        return `
          <span class="badge bg-${v}-lt text-${v} fw-normal">
            <i class="ti ${escapeHtml(icon)} me-1"></i>
            ${escapeHtml(text)}
          </span>
        `;
      };

      for (const route of items) {
        const el = document.createElement("button");
        el.type = "button";
        el.className = "list-group-item list-group-item-action text-start py-2";

        const cargo = route.cargo_name || "";
        const cargoGroup = route.cargo_group_name || "";
        const holding = route.shipper_holding || "";
        const origin = route.origin_station_name || "";
        const destination = route.destination_station_name || "";
        const msgType = route.message_type_name || "";
        const wagonKind = (route.wagon_kind_name || "").trim();

        const badges = [
          badge(cargo, "ti-box", "lime"),
          badge(cargoGroup, "ti-category", "teal"),
          badge(holding, "ti-building", "indigo"),
          badge(wagonKind, "ti-truck", "orange"),
          badge(msgType, "ti-message", "azure"),
        ]
          .filter(Boolean)
          .join("");

        el.innerHTML = `
          <div class="d-flex flex-column gap-1 min-w-0">
            <div class="fw-medium small text-truncate">${escapeHtml(origin)} → ${escapeHtml(destination)}</div>
            <div class="d-flex flex-wrap align-items-center gap-1">
              ${badges}
            </div>
          </div>
        `;

        el.addEventListener("click", () => {
          for (const btn of listEl.querySelectorAll("button")) {
            btn.classList.remove("active");
          }
          el.classList.add("active");
          this.state.pendingSelectedRoute = route;
          this._setConfirmEnabled(true);
        });

        listEl.appendChild(el);
      }
    }

    _resolveEnterpriseLoadCoefficient(route) {
      if (!route) return null;
      const own = route.enterprise_load_coefficient;
      if (own != null && own !== "" && Number(own) !== 0) {
        return own;
      }
      const fromModel = route.enterprise_load_coefficient_from_model;
      if (fromModel != null && fromModel !== "" && Number(fromModel) !== 0) {
        return fromModel;
      }
      return null;
    }

    _formatEnterpriseLoadCoefficient(value) {
      const num = Number(value);
      if (!Number.isFinite(num) || num === 0) return "";
      const pct = num * 100;
      const pctText = pct.toLocaleString("ru-RU", {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2,
      });
      return `${pctText}%`;
    }

    _shouldShowEnterpriseLoadCoefficient(route) {
      const scenario = this.state.selectedScenario;
      if (!scenario || scenario.consider_enterprise_load === false) {
        return false;
      }
      return this._resolveEnterpriseLoadCoefficient(route) != null;
    }

    _renderRouteDetails(route) {
      const detailsEl = document.getElementById("routeAnalysisRouteDetails");
      if (!detailsEl) return;

      if (!route) {
        detailsEl.innerHTML = `
          <div class="text-muted">
            Маршрут не выбран.
          </div>
        `;
        return;
      }

      const routeCode = (route.route_code || "").trim();
      const cargo = (route.cargo_name || "").trim();
      const cargoGroup = (route.cargo_group_name || "").trim();
      const shipper = (route.shipper_name || "").trim();
      const holding = (route.shipper_holding || "").trim();
      const origin = (route.origin_station_name || "").trim();
      const destination = (route.destination_station_name || "").trim();
      const msgType = (route.message_type_name || "").trim();
      const wagonKind = (route.wagon_kind_name || "").trim();
      const shipmentType = (route.shipment_type_name || "").trim();
      const enterpriseLoadRaw = this._shouldShowEnterpriseLoadCoefficient(route)
        ? this._resolveEnterpriseLoadCoefficient(route)
        : null;
      const enterpriseLoad = enterpriseLoadRaw
        ? this._formatEnterpriseLoadCoefficient(enterpriseLoadRaw)
        : "";

      const pill = (text, icon, variant) => {
        if (!text) return "";
        const v = variant || "azure";
        return `
          <span class="badge bg-${v}-lt text-${v} me-2 mb-2">
            <i class="ti ${escapeHtml(icon)} me-1"></i>
            ${escapeHtml(text)}
          </span>
        `;
      };

      const row = (label, value, icon, showEmpty = false) => {
        const displayValue = (value || "").trim();
        if (!displayValue && !showEmpty) return "";
        return `
          <div class="d-flex align-items-start gap-2 mb-2">
            <div class="text-muted" style="width: 140px;">
              <i class="ti ${escapeHtml(icon)} me-1"></i>
              ${escapeHtml(label)}
            </div>
            <div class="fw-medium text-body flex-grow-1">
              ${escapeHtml(displayValue || "—")}
            </div>
          </div>
        `;
      };

      const headerBadges = [
        pill(cargoGroup, "ti-category", "teal"),
        pill(msgType, "ti-message", "azure"),
      ]
        .filter(Boolean)
        .join("");

      detailsEl.classList.remove("text-muted");
      detailsEl.innerHTML = `
        <div class="border rounded-3 p-3 bg-light-subtle">
          <div class="d-flex align-items-start justify-content-between gap-2">
            <div>
              <div class="text-muted small mb-1">Код маршрута</div>
              <div class="fw-bold">${escapeHtml(routeCode || "—")}</div>
            </div>
            <div class="text-end">
              ${headerBadges}
            </div>
          </div>

          ${cargo ? `<div class="mt-3">${row("Груз", cargo, "ti-box")}</div>` : ""}

          <div class="mt-2">
            ${row("Грузоотправитель", shipper, "ti-user", true)}
            ${row("Холдинг", holding, "ti-building", true)}
          </div>

          <div class="mt-2">
            ${row("Отправление", origin, "ti-map-pin")}
            ${row("Назначение", destination, "ti-flag")}
          </div>

          <div class="mt-2">
            ${row("Род вагона", wagonKind, "ti-truck")}
            ${row("Тип отправки", shipmentType, "ti-send")}
            ${enterpriseLoad ? row("Загрузка предприятия", enterpriseLoad, "ti-gauge") : ""}
          </div>
        </div>
      `;
    }

    async _renderDiagram() {
      const chartWrapEl = document.getElementById("routeAnalysisTrendsChartWrap");
      const chartCanvas = document.getElementById("routeAnalysisTrendsChart");
      const tableWrapEl = document.getElementById(
        "routeAnalysisStructureTableWrap",
      );
      const effectsWrapEl = document.getElementById("routeAnalysisEffectsTableWrap");
      const kpiWrapEl = document.getElementById("routeAnalysisKpiWrap");
      const placeholderEl =
        this.hasDiagramPlaceholderTarget
          ? this.diagramPlaceholderTarget
          : document.getElementById("routeAnalysisDiagramPlaceholder");

      const typeSelect =
        this.hasDiagramTypeSelectTarget ? this.diagramTypeSelectTarget : null;
      const typeValue = typeSelect ? typeSelect.value : "trends";

      const showPlaceholder = (html) => {
        this._hideDiagramExtras();
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (effectsWrapEl) {
          effectsWrapEl.style.display = "none";
          effectsWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) {
          kpiWrapEl.style.display = "none";
          kpiWrapEl.innerHTML = "";
        }
        if (this.state.trendsChart) {
          try {
            this.state.trendsChart.destroy();
          } catch (_e) {
            // ignore
          }
          this.state.trendsChart = null;
        }
        if (placeholderEl) {
          placeholderEl.style.display = "";
          placeholderEl.innerHTML = html;
        }
      };

      const showChart = () => {
        this._hideDiagramExtras();
        if (placeholderEl) placeholderEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (effectsWrapEl) {
          effectsWrapEl.style.display = "none";
          effectsWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) {
          kpiWrapEl.style.display = "none";
          kpiWrapEl.innerHTML = "";
        }
        if (chartWrapEl) chartWrapEl.style.display = "";
      };

      const showTable = () => {
        this._hideDiagramExtras();
        if (placeholderEl) placeholderEl.style.display = "none";
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (effectsWrapEl) {
          effectsWrapEl.style.display = "none";
          effectsWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) {
          kpiWrapEl.style.display = "none";
          kpiWrapEl.innerHTML = "";
        }
        if (tableWrapEl) tableWrapEl.style.display = "";
      };

      const showEffects = () => {
        this._hideDiagramExtras();
        if (placeholderEl) placeholderEl.style.display = "none";
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) {
          kpiWrapEl.style.display = "none";
          kpiWrapEl.innerHTML = "";
        }
        if (effectsWrapEl) effectsWrapEl.style.display = "";
      };

      const showKpi = () => {
        this._hideDiagramExtras();
        if (placeholderEl) placeholderEl.style.display = "none";
        if (chartWrapEl) chartWrapEl.style.display = "none";
        if (tableWrapEl) {
          tableWrapEl.style.display = "none";
          tableWrapEl.innerHTML = "";
        }
        if (effectsWrapEl) {
          effectsWrapEl.style.display = "none";
          effectsWrapEl.innerHTML = "";
        }
        if (kpiWrapEl) kpiWrapEl.style.display = "";
      };

      if (!this.state.selectedRoute) {
        showPlaceholder(`
          <div class="mb-2">
            <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
          </div>
          <div>Выберите маршрут для отображения диаграммы</div>
        `);
        return;
      }

      if (typeValue === "structure_table") {
        const scenarioId = this.state.selectedScenarioId;
        const routeId = this.state.selectedRoute ? this.state.selectedRoute.id : null;

        if (!scenarioId || !routeId) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Не удалось определить сценарий и маршрут для построения таблицы.</div>
          `);
          return;
        }

        showTable();
        await this._renderStructureTable({
          scenarioId,
          routeId,
          containerEl: tableWrapEl,
        });
        return;
      }

      if (typeValue === "decision_effects") {
        showEffects();
        if (effectsWrapEl) {
          effectsWrapEl.innerHTML = `
            <div class="text-center text-muted py-4">
              <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
              <div class="mt-2">Расчёт эффектов…</div>
            </div>
          `;
        }
        const result = await this._fetchRouteAnalysisData({});
        if (!result.ok) {
          showPlaceholder(`
            <div class="alert alert-danger" role="alert">
              ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
            </div>
          `);
          return;
        }
        showEffects();
        this._renderEffectsTable(effectsWrapEl, result.data);
        return;
      }

      if (typeValue === "kpi") {
        showKpi();
        if (kpiWrapEl) {
          kpiWrapEl.innerHTML = `
            <div class="text-center text-muted py-4 w-100">
              <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
              <div class="mt-2">Расчёт KPI…</div>
            </div>
          `;
        }
        const result = await this._fetchRouteAnalysisData({});
        if (!result.ok) {
          showPlaceholder(`
            <div class="alert alert-danger" role="alert">
              ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
            </div>
          `);
          return;
        }
        showKpi();
        this._renderKpiCards(kpiWrapEl, result.data);
        return;
      }

      if (typeValue === "rzd_tariff_sensitivity") {
        if (!chartCanvas) return;
        if (typeof window.Chart === "undefined") {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-alert-triangle" style="font-size: 2rem;"></i>
            </div>
            <div>Chart.js не загружен. Обновите страницу.</div>
          `);
          return;
        }

        showPlaceholder(`
          <div class="text-center text-muted py-4">
            <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
            <div class="mt-2">Расчёт чувствительности к тарифу РЖД…</div>
          </div>
        `);

        const result = await this._fetchRouteAnalysisData({});
        if (!result.ok) {
          showPlaceholder(`
            <div class="alert alert-danger" role="alert">
              ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
            </div>
          `);
          return;
        }

        const points =
          result.data &&
          result.data.rzd_tariff_sensitivity &&
          Array.isArray(result.data.rzd_tariff_sensitivity.points)
            ? result.data.rzd_tariff_sensitivity.points
            : [];

        if (!points.length || points.every((point) => point.coefficient == null)) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Для маршрута нет данных эластичности для построения диаграммы.</div>
          `);
          return;
        }

        showChart();
        const ctx = chartCanvas.getContext("2d");
        this._renderRzdTariffSensitivityChart(ctx, points);
        return;
      }

      if (!chartCanvas) return;
      if (typeof window.Chart === "undefined") {
        showPlaceholder(`
          <div class="mb-2">
            <i class="ti ti-alert-triangle" style="font-size: 2rem;"></i>
          </div>
          <div>Chart.js не загружен. Обновите страницу.</div>
        `);
        return;
      }

      const scenario = this.state.selectedScenario;
      const startYear = scenario && scenario.start_year ? Number(scenario.start_year) : null;
      const endYear = scenario && scenario.end_year ? Number(scenario.end_year) : null;
      if (!startYear || !endYear || Number.isNaN(startYear) || Number.isNaN(endYear)) {
        showPlaceholder(`
          <div class="mb-2">
            <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
          </div>
          <div>Не удалось определить годы сценария для построения графика.</div>
        `);
        return;
      }

      const years = [];
      for (let y = startYear; y <= endYear; y += 1) years.push(y);

      const toNum = (val) => {
        if (val == null) return null;
        const n = Number(String(val).replace(",", "."));
        return Number.isFinite(n) ? n : null;
      };

      const formatBox = (num) =>
        String(Math.round(num)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");

      showChart();

      // eslint-disable-next-line no-undef
      const ChartDataLabelsPlugin =
        window.ChartDataLabels || window.ChartDataLabelsPlugin || null;
      if (ChartDataLabelsPlugin && window.Chart) {
        // eslint-disable-next-line no-undef
        window.Chart.register(ChartDataLabelsPlugin);
      }

      if (this.state.trendsChart) {
        try {
          this.state.trendsChart.destroy();
        } catch (_e) {
          // ignore
        }
        this.state.trendsChart = null;
      }

      const ctx = chartCanvas.getContext("2d");

      const commonPlugins = {
        legend: {
          position: "bottom",
          labels: {
            boxWidth: 18,
            boxHeight: 10,
          },
        },
        tooltip: {
          enabled: true,
          mode: "index",
          intersect: false,
          axis: "x",
        },
      };

      const commonInteraction = {
        mode: "index",
        intersect: false,
      };

      if (typeValue === "trends") {
        const scenarioId = this.state.selectedScenarioId;
        const routeId = this.state.selectedRoute ? this.state.selectedRoute.id : null;
        let calculateData = null;

        if (scenarioId && routeId) {
          showPlaceholder(`
            <div class="text-center text-muted py-4">
              <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
              <div class="mt-2">Расчёт трендов…</div>
            </div>
          `);
          let result;
          try {
            result = await this._loadRouteAnalysis({
              scenarioId,
              routeId,
              overrides: this._buildOverridesPayload(),
            });
          } catch (_e) {
            showPlaceholder(`
              <div class="mb-2">
                <i class="ti ti-alert-triangle" style="font-size: 2rem;"></i>
              </div>
              <div>Ошибка расчёта трендов (см. консоль).</div>
            `);
            return;
          }
          if (!result.ok) {
            showPlaceholder(`
              <div class="alert alert-danger" role="alert">
                ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
              </div>
            `);
            return;
          }
          calculateData = result.data;
        }

        const rowValuesByKey = (rowKey) => this._rowValuesByKey(calculateData, rowKey);

        const series = [
          { rowKey: "price_rub", name: "Цена тонны", color: "#1f6feb" },
          { rowKey: "cost", name: "Себестоимость", color: "#2da44e" },
          { rowKey: "rzd", name: "РЖД (итого), руб./т", color: "#8250df" },
          { rowKey: "operators", name: "Операторы, руб./т", color: "#d29922" },
          { rowKey: "transshipment", name: "Перевалка, руб./т", color: "#bc4c00" },
        ];

        const datasets = [];
        for (const s of series) {
          let dataPoints = rowValuesByKey(s.rowKey);
          if (!dataPoints) {
            const fallbackKeys = {
              price_rub: "market_price_per_ton",
              cost: "production_cost_per_ton",
              operators: "operators_cost_per_ton",
              transshipment: "transshipment_cost_per_ton",
              rzd: "rzd_cost_total_per_ton",
            };
            const routeKey = fallbackKeys[s.rowKey];
            const v = routeKey ? toNum(this.state.selectedRoute[routeKey]) : null;
            dataPoints = v != null ? years.map(() => v) : null;
          }
          if (!dataPoints || dataPoints.every((v) => v == null)) continue;
          datasets.push({
            label: s.name,
            data: dataPoints.map((v) => (v != null ? v : 0)),
            borderColor: s.color,
            backgroundColor: s.color,
            borderWidth: 3,
            pointRadius: 4,
            pointHoverRadius: 5,
            tension: 0,
          });
        }

        if (datasets.length === 0) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Для выбранного маршрута нет данных для построения трендов.</div>
          `);
          return;
        }

        showChart();

        this.state.trendsChart = new window.Chart(ctx, {
          type: "line",
          data: {
            labels: years,
            datasets,
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            layout: {
              // Запас сверху, чтобы подписи в рамочке не упирались в край canvas.
              padding: { top: 24 },
            },
            plugins: {
              ...commonPlugins,
              title: {
                display: true,
                text: "Тренды по маршруту",
                align: "start",
                font: { size: 16, weight: "600" },
                padding: { bottom: 12 },
              },
              datalabels: {
                display: true,
                formatter: (value) => formatBox(value),
                anchor: "end",
                align: "top",
                offset: 8,
                backgroundColor: "#ffffff",
                borderColor: "#d0d7de",
                borderWidth: 1,
                borderRadius: 5,
                padding: { top: 2, bottom: 2, left: 6, right: 6 },
                color: "#111827",
                font: { size: 10, weight: "600" },
                clamp: true,
                clip: false,
              },
            },
            interaction: commonInteraction,
            scales: {
              x: {
                title: { display: true, text: "Год" },
                grid: { display: false },
                border: { display: false },
              },
              y: {
                grid: { display: false },
                border: { display: false },
                ticks: { display: false },
              },
            },
            elements: {
              line: { tension: 0 },
            },
          },
        });

        return;
      }

      if (typeValue === "structure") {
        const scenarioId = this.state.selectedScenarioId;
        const routeId = this.state.selectedRoute ? this.state.selectedRoute.id : null;
        let calculateData = this.state.activeCalculateData;

        if (scenarioId && routeId && !calculateData) {
          showPlaceholder(`
            <div class="text-center text-muted py-4">
              <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
              <div class="mt-2">Расчёт структуры…</div>
            </div>
          `);
          let result;
          try {
            result = await this._loadRouteAnalysis({
              scenarioId,
              routeId,
              overrides: this._buildOverridesPayload(),
            });
          } catch (_e) {
            showPlaceholder(`
              <div class="mb-2">
                <i class="ti ti-alert-triangle" style="font-size: 2rem;"></i>
              </div>
              <div>Ошибка расчёта структуры (см. консоль).</div>
            `);
            return;
          }
          if (!result.ok) {
            showPlaceholder(`
              <div class="alert alert-danger" role="alert">
                ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
              </div>
            `);
            return;
          }
          calculateData = result.data;
        }

        const yearParts = years.map((_y, index) =>
          this._structurePartsForYearIndex(calculateData, index),
        );
        if (yearParts.some((p) => !p)) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Для структуры нужна «Цена тонны» у маршрута.</div>
          `);
          return;
        }

        const partNames = yearParts[0].map((p) => p.name);
        const datasets = partNames.map((name, partIndex) => {
          const sample = yearParts[0][partIndex];
          return {
            label: name,
            data: yearParts.map((parts) => parts[partIndex].valuePct),
            borderColor: sample.color,
            backgroundColor: sample.color,
            borderWidth: 0,
            borderRadius: 4,
            barPercentage: 0.8,
            categoryPercentage: 0.8,
            stack: "stack",
          };
        });

        showChart();

        this.state.trendsChart = new window.Chart(ctx, {
          type: "bar",
          data: { labels: years, datasets },
          options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              ...commonPlugins,
              title: {
                display: true,
                text: "Структура по годам",
                align: "start",
                font: { size: 16, weight: "600" },
                padding: { bottom: 12 },
              },
              datalabels: {
                display: (ctx) => {
                  const v = ctx.dataset.data[ctx.dataIndex];
                  return v != null && Number(v) >= 6;
                },
                formatter: (value) => `${Number(value).toFixed(2)}%`,
                anchor: "center",
                align: "center",
                backgroundColor: "#ffffff",
                borderColor: "#d0d7de",
                borderWidth: 1,
                borderRadius: 5,
                padding: { top: 2, bottom: 2, left: 6, right: 6 },
                color: "#111827",
                font: { size: 10, weight: "600" },
                clamp: true,
              },
              tooltip: {
                enabled: true,
                callbacks: {
                  label: (ctx) => `${ctx.dataset.label}: ${Number(ctx.raw).toFixed(2)}%`,
                },
              },
            },
            interaction: {
              mode: "index",
              intersect: false,
              axis: "y",
            },
            scales: {
              x: {
                min: 0,
                max: 100,
                stacked: true,
                grid: { display: false },
                border: { display: false },
                ticks: {
                  callback: (v) => `${v}%`,
                },
              },
              y: {
                stacked: true,
                grid: { display: false },
                border: { display: false },
                title: { display: true, text: "Год" },
              },
            },
          },
        });

        return;
      }

      if (typeValue === "structure_aggregated" || typeValue === "structure_ts") {
        showPlaceholder(`
          <div class="text-center text-muted py-4">
            <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
            <div class="mt-2">Расчёт структуры…</div>
          </div>
        `);
        const result = await this._fetchRouteAnalysisData({});
        if (!result.ok) {
          showPlaceholder(`
            <div class="alert alert-danger" role="alert">
              ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
            </div>
          `);
          return;
        }
        const calculateData = result.data;
        const apiYears = Array.isArray(calculateData.years) ? calculateData.years : years;

        if (this.state.trendsChart) {
          try {
            this.state.trendsChart.destroy();
          } catch (_e) {
            // ignore
          }
          this.state.trendsChart = null;
        }

        if (typeValue === "structure_aggregated") {
          const gdfRows = apiYears.map((_year, index) => {
            const costsRub = this._rowRubByKey(calculateData, "cost", index);
            const transportRub = this._rowRubByKey(calculateData, "transport", index);
            const marginRub = this._rowRubByKey(calculateData, "marginality", index);
            const sum = costsRub + transportRub + marginRub;
            if (sum <= 0) {
              return {
                costs: 0,
                transport: 0,
                marginality: 0,
                costsRub: 0,
                transportRub: 0,
                marginRub: 0,
              };
            }
            return {
              costs: (costsRub / sum) * 100,
              transport: (transportRub / sum) * 100,
              marginality: (marginRub / sum) * 100,
              costsRub,
              transportRub,
              marginRub,
            };
          });
          const fakeRows = this._fakeGdfTr(gdfRows);
          const segmentDefs = [
            {
              key: "costs",
              label: "Себестоимость производства",
              color: "#4fb4ff",
              rubKey: "costsRub",
            },
            {
              key: "transport",
              label: "Транспортная составляющая",
              color: "#0091fe",
              rubKey: "transportRub",
            },
            {
              key: "marginality",
              label: "Маржинальность холдинга",
              color: "#003256",
              rubKey: "marginRub",
            },
          ];
          const datasets = segmentDefs.map((segment) => ({
            label: segment.label,
            data: fakeRows.map((row) => row[segment.key]),
            realPct: gdfRows.map((row) => row[segment.key]),
            rubValues: gdfRows.map((row) => row[segment.rubKey]),
            backgroundColor: segment.color,
            borderColor: segment.color,
            borderWidth: 0,
            stack: "stack",
          }));

          showChart();
          this.state.trendsChart = new window.Chart(ctx, {
            type: "bar",
            data: { labels: apiYears, datasets },
            options: {
              responsive: true,
              maintainAspectRatio: false,
              plugins: {
                ...commonPlugins,
                title: {
                  display: true,
                  text: "Структура укрупнённая",
                  align: "start",
                  font: { size: 16, weight: "600" },
                  padding: { bottom: 12 },
                },
                datalabels: {
                  display: (ctx) => {
                    const real = ctx.dataset.realPct[ctx.dataIndex];
                    return real != null && Number(real) >= 4;
                  },
                  formatter: (_value, ctx) => {
                    const real = ctx.dataset.realPct[ctx.dataIndex];
                    return `${Number(real).toFixed(1)}%`;
                  },
                  anchor: "center",
                  align: "center",
                  color: "#ffffff",
                  font: { size: 11, weight: "600" },
                },
                tooltip: {
                  enabled: true,
                  callbacks: {
                    label: (ctx) => {
                      const rub = ctx.dataset.rubValues[ctx.dataIndex];
                      const pct = ctx.dataset.realPct[ctx.dataIndex];
                      return `${ctx.dataset.label}: ${formatBox(rub)} руб. (${Number(pct).toFixed(1)}%)`;
                    },
                  },
                },
              },
              interaction: commonInteraction,
              scales: {
                x: { stacked: true, grid: { display: false } },
                y: {
                  stacked: true,
                  max: 100,
                  grid: { display: false },
                  ticks: { display: false },
                },
              },
            },
          });
          return;
        }

        const ts = calculateData.transport_structure;
        if (!ts) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Нет данных транспортной структуры.</div>
          `);
          return;
        }

        const rzdLoaded = this._mapYearValues(ts.rzd_loaded_by_year, apiYears);
        const rzdEmpty = this._mapYearValues(ts.rzd_empty_by_year, apiYears);
        const operators = apiYears.map((_y, index) =>
          this._rowRubByKey(calculateData, "operators", index),
        );
        const transshipment = apiYears.map((_y, index) =>
          this._rowRubByKey(calculateData, "transshipment", index),
        );

        const tsSegments = [
          {
            label: 'Расходы на оплату услуг ОАО "РЖД" (гружёный рейс)',
            data: rzdLoaded,
            color: "#0091fe",
            visible: true,
          },
        ];
        if (ts.show_empty_leg) {
          tsSegments.push({
            label: 'Расходы на оплату услуг ОАО "РЖД" (порожний рейс)',
            data: rzdEmpty,
            color: "#4fb4ff",
            visible: true,
          });
        }
        tsSegments.push(
          {
            label: "Расходы по оплате услуг операторов",
            data: operators,
            color: "#0072c8",
            visible: operators.some((v) => v > 0),
          },
          {
            label: "Расходы на перевалку",
            data: transshipment,
            color: "#005da2",
            visible: transshipment.some((v) => v > 0),
          },
        );

        const datasets = tsSegments
          .filter((segment) => segment.visible)
          .map((segment) => ({
            label: segment.label,
            data: segment.data,
            backgroundColor: segment.color,
            borderColor: segment.color,
            borderWidth: 0,
            stack: "stack",
          }));

        if (datasets.length === 0) {
          showPlaceholder(`
            <div class="mb-2">
              <i class="ti ti-info-circle" style="font-size: 2rem;"></i>
            </div>
            <div>Нет данных для структуры ТС.</div>
          `);
          return;
        }

        showChart();
        this._renderTsAnnotations(apiYears, ts);
        this.state.trendsChart = new window.Chart(ctx, {
          type: "bar",
          data: { labels: apiYears, datasets },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              ...commonPlugins,
              title: {
                display: true,
                text: "Структура ТС",
                align: "start",
                font: { size: 16, weight: "600" },
                padding: { bottom: 12 },
              },
              datalabels: {
                display: (ctx) => {
                  const v = ctx.dataset.data[ctx.dataIndex];
                  return v != null && Number(v) > 0;
                },
                formatter: (value) => Number(value).toFixed(1),
                anchor: "center",
                align: "center",
                color: "#ffffff",
                font: { size: 10, weight: "600" },
              },
              tooltip: {
                enabled: true,
                callbacks: {
                  label: (ctx) =>
                    `${ctx.dataset.label}: ${formatBox(ctx.raw)} руб./т`,
                },
              },
            },
            interaction: commonInteraction,
            scales: {
              x: { stacked: true, grid: { display: false } },
              y: {
                stacked: true,
                grid: { display: false },
                ticks: {
                  callback: (v) => formatBox(v),
                },
              },
            },
          },
        });
      }
    }


    _setConfirmEnabled(enabled) {
      const btn = this._getConfirmButtonEl();
      if (!btn) return;
      // Важно: некоторые браузеры/шаблоны могут сохранять HTML-атрибут disabled,
      // поэтому снимаем его явно.
      btn.disabled = !enabled;
      if (enabled) {
        btn.removeAttribute("disabled");
      } else {
        btn.setAttribute("disabled", "disabled");
      }
    }

    _setLoading(loading) {
      const el = this._getLoadingEl();
      if (!el) return;
      setVisible(el, !!loading);
    }

    _showErrors(errors) {
      const el = this._getErrorsEl();
      if (!el) return;
      const list = (errors || []).filter(Boolean);
      if (list.length === 0) {
        el.classList.add("d-none");
        el.textContent = "";
        return;
      }
      el.classList.remove("d-none");
      el.textContent = list.join("\n");
    }

    _resetUi() {
      this._showErrors([]);
      this._setLoading(false);
      const emptyEl = this._getEmptyEl();
      if (emptyEl) setVisible(emptyEl, false);
      const listEl = this._getRouteListEl();
      if (listEl) listEl.innerHTML = "";
      this._setConfirmEnabled(false);
      this.state.pendingSelectedRoute = null;
      this._resetCascadeFilters();
      this._resetRoutesPagination();
    }

    _onRouteListScroll() {
      const listEl = this._getRouteListEl();
      if (!listEl) return;
      if (!this.state.routesHasNext || this.state.routesIsLoadingMore) return;

      const threshold = 80;
      const distanceToBottom =
        listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight;
      if (distanceToBottom > threshold) return;

      this._loadRoutes({
        search: this.state.routesLastSearch,
        cascade: this.state.routesLastCascade,
        page: this.state.routesPage + 1,
        append: true,
      });
    }

    _showLoadMoreSentinel() {
      const listEl = this._getRouteListEl();
      if (!listEl) return;
      this._removeLoadMoreSentinel();
      const sentinel = document.createElement("div");
      sentinel.className =
        "list-group-item text-center py-3 text-muted route-list-loadmore";
      sentinel.setAttribute("data-route-list-loadmore", "");
      sentinel.innerHTML = `
        <div class="spinner-border spinner-border-sm me-2" role="status">
          <span class="visually-hidden">Загрузка...</span>
        </div>
        Загрузка…
      `;
      listEl.appendChild(sentinel);
    }

    _removeLoadMoreSentinel() {
      const listEl = this._getRouteListEl();
      if (!listEl) return;
      const sentinel = listEl.querySelector("[data-route-list-loadmore]");
      if (sentinel) sentinel.remove();
    }

    _ensureModalHandlers() {
      const input = this._getSearchInputEl();
      if (input) {
        // Если Stimulus data-action не сработал (например, модалка перенесена в body),
        // подключаем обработчик вручную.
        input.removeEventListener("input", this.state.boundSearchHandler);
        input.addEventListener("input", this.state.boundSearchHandler);
      }

      const okBtn = this._getConfirmButtonEl();
      if (okBtn) {
        if (!this.state.boundConfirmHandler) {
          this.state.boundConfirmHandler = this.confirmSelection.bind(this);
        }
        okBtn.removeEventListener("click", this.state.boundConfirmHandler);
        okBtn.addEventListener("click", this.state.boundConfirmHandler);
      }

      const listEl = this._getRouteListEl();
      if (listEl) {
        if (!this.state.boundScrollHandler) {
          this.state.boundScrollHandler = this._onRouteListScroll.bind(this);
        }
        listEl.removeEventListener("scroll", this.state.boundScrollHandler);
        listEl.addEventListener("scroll", this.state.boundScrollHandler);
      }

      const filtersBtn = document.getElementById("routeAnalysisFiltersToggle");
      if (filtersBtn) {
        if (!this.state.boundFiltersToggleHandler) {
          this.state.boundFiltersToggleHandler = (event) => {
            this.toggleFilters(event);
          };
        }
        filtersBtn.removeEventListener("click", this.state.boundFiltersToggleHandler);
        filtersBtn.addEventListener("click", this.state.boundFiltersToggleHandler);
      }

      const searchBtn = document.getElementById("routeAnalysisSearchToggle");
      if (searchBtn) {
        if (!this.state.boundSearchToggleHandler) {
          this.state.boundSearchToggleHandler = (event) => {
            this.toggleSearch(event);
          };
        }
        searchBtn.removeEventListener("click", this.state.boundSearchToggleHandler);
        searchBtn.addEventListener("click", this.state.boundSearchToggleHandler);
      }

      this._bindFiltersCollapseListener();
      this._bindSearchCollapseListener();
    }

    _getCascadeSelectEl(targetName) {
      const hasTargetKey = `has${targetName.charAt(0).toUpperCase()}${targetName.slice(1)}Target`;
      if (this[hasTargetKey]) {
        return this[`${targetName}Target`];
      }
      const modal = this._getModalEl();
      const elementId = this.constructor.CASCADE_SELECT_IDS[targetName];
      if (modal && elementId) {
        return modal.querySelector(`#${elementId}`);
      }
      return null;
    }

    _getCascadeTomSelectKey(chainItem) {
      return `${this._getPickerMode()}:${chainItem.targetName}`;
    }

    _readCascadeFromTomSelects() {
      const chain = this._getActiveCascadeChain();
      const next = this._emptyCascade();
      for (const item of chain) {
        const key = this._getCascadeTomSelectKey(item);
        const instance = this.state.cascadeTomSelects[key];
        const value = instance ? String(instance.getValue() || "").trim() : "";
        next[item.key] = value;
      }
      this.state.cascade = next;
      return next;
    }

    _resetCascadeFilters() {
      this.state.cascade = this._emptyCascade();
      const chain = this._getActiveCascadeChain();
      for (const item of chain) {
        const key = this._getCascadeTomSelectKey(item);
        const instance = this.state.cascadeTomSelects[key];
        if (instance) {
          instance.clear(true);
        }
        const selectEl = this._getCascadeSelectEl(item.targetName);
        if (selectEl) {
          selectEl.disabled = item.key !== chain[0].key;
        }
      }
    }

    _resetCascadeDownstream(changedKey) {
      const chain = this._getActiveCascadeChain();
      const startIndex = chain.findIndex((item) => item.key === changedKey);
      if (startIndex < 0) return;

      for (let index = startIndex + 1; index < chain.length; index += 1) {
        const item = chain[index];
        this.state.cascade[item.key] = "";
        const key = this._getCascadeTomSelectKey(item);
        const instance = this.state.cascadeTomSelects[key];
        if (instance) {
          instance.clear(true);
          instance.clearOptions();
          instance.disable();
        }
        const selectEl = this._getCascadeSelectEl(item.targetName);
        if (selectEl) {
          selectEl.disabled = true;
        }
      }
    }

    _syncCascadeEnabledState() {
      const chain = this._getActiveCascadeChain();
      let previousFilled = true;
      for (const item of chain) {
        const key = this._getCascadeTomSelectKey(item);
        const instance = this.state.cascadeTomSelects[key];
        const selectEl = this._getCascadeSelectEl(item.targetName);
        const enabled = previousFilled;
        if (selectEl) {
          selectEl.disabled = !enabled;
        }
        if (instance) {
          if (enabled) {
            instance.enable();
          } else {
            instance.disable();
          }
        }
        const value = this.state.cascade[item.key] || "";
        previousFilled = Boolean(enabled && value);
      }
    }

    _preloadNextCascadeField(changedKey) {
      const chain = this._getActiveCascadeChain();
      const changedIndex = chain.findIndex((item) => item.key === changedKey);
      if (changedIndex < 0 || changedIndex >= chain.length - 1) return;
      if (!this.state.cascade[changedKey]) return;

      const nextItem = chain[changedIndex + 1];
      const nextKey = this._getCascadeTomSelectKey(nextItem);
      const nextInstance = this.state.cascadeTomSelects[nextKey];
      if (nextInstance && typeof nextInstance.load === "function") {
        nextInstance.load("");
      }
    }

    _buildPickerOptionsParams(dimension) {
      const params = new URLSearchParams();
      params.set("route_set_id", String(this.state.selectedRouteSetId));
      params.set("dimension", dimension);
      params.set("economics_filled", "1");

      const mode = this._getPickerMode();
      const cascade = this.state.cascade;
      if (mode === "cargo_first") {
        if (["cargo", "transport_type", "holding"].includes(dimension) && cascade.cargoGroup) {
          params.set("cargo_group_name", cascade.cargoGroup);
        }
        if (["transport_type", "holding"].includes(dimension) && cascade.cargo) {
          params.set("cargo_code", cascade.cargo);
        }
        if (dimension === "holding" && cascade.transportType) {
          params.set("message_type_name", cascade.transportType);
        }
      } else if (["transport_type", "cargo"].includes(dimension) && cascade.holding) {
        params.set("holding", cascade.holding);
        if (dimension === "cargo" && cascade.transportType) {
          params.set("message_type_name", cascade.transportType);
        }
      }
      return params;
    }

    _ensureCascadeTomSelects() {
      if (this.state.cascadeTomSelectInitialized) {
        this._syncCascadeEnabledState();
        return;
      }
      const TomSelectCtor = window.TomSelect;
      if (typeof TomSelectCtor === "undefined") {
        console.warn("TomSelect is not available for route-analysis cascade filters");
        return;
      }
      if (!this.pickerOptionsUrlValue) {
        console.warn("pickerOptionsUrlValue is not defined for route-analysis");
        return;
      }
      if (!this.state.selectedRouteSetId) {
        console.warn("[route-analysis] cascade filters: route_set_id is empty");
        return;
      }

      const chain = this._getActiveCascadeChain();
      const pickerOptionsUrl = this.pickerOptionsUrlValue;
      let initializedCount = 0;

      for (let chainIndex = 0; chainIndex < chain.length; chainIndex += 1) {
        const item = chain[chainIndex];
        const selectEl = this._getCascadeSelectEl(item.targetName);
        if (!selectEl) continue;

        const storageKey = this._getCascadeTomSelectKey(item);
        if (selectEl.tomselect) {
          this.state.cascadeTomSelects[storageKey] = selectEl.tomselect;
          initializedCount += 1;
          continue;
        }

        const dimension = item.dimension;
        const cascadeKey = item.key;
        const controller = this;
        const isFirstInChain = chainIndex === 0;

        this.state.cascadeTomSelects[storageKey] = new TomSelectCtor(selectEl, {
          valueField: "value",
          labelField: "text",
          searchField: ["text"],
          maxOptions: 50,
          maxItems: 1,
          loadThrottle: 350,
          preload: isFirstInChain ? true : "focus",
          shouldLoad: () => true,
          placeholder: selectEl.getAttribute("placeholder") || "",
          render: {
            option(optionItem, escape) {
              return `<div>${escape(optionItem.text || "")}</div>`;
            },
            item(optionItem, escape) {
              return `<div>${escape(optionItem.text || "")}</div>`;
            },
            no_results() {
              return '<div class="no-results">Ничего не найдено</div>';
            },
          },
          load(query, callback) {
            if (!controller.state.selectedRouteSetId) {
              callback();
              return;
            }
            const params = controller._buildPickerOptionsParams(dimension);
            const q = (query || "").trim();
            if (q) {
              params.set("search", q);
            }
            fetchJson(`${pickerOptionsUrl}?${params.toString()}`, { method: "GET" })
              .then(({ data }) => {
                if (!data || !data.success || !Array.isArray(data.items)) {
                  callback();
                  return;
                }
                callback(
                  data.items.map((option) => ({
                    value: String(option.value),
                    text: option.text || option.value,
                  })),
                );
              })
              .catch((error) => {
                console.error("Ошибка загрузки опций фильтра:", error);
                callback();
              });
          },
          onChange(value) {
            controller.state.cascade[cascadeKey] = value
              ? String(value).trim()
              : "";
            controller._resetCascadeDownstream(cascadeKey);
            controller._readCascadeFromTomSelects();
            controller._syncCascadeEnabledState();
            controller._preloadNextCascadeField(cascadeKey);
            controller.onCascadeFilterChange();
          },
        });
        initializedCount += 1;
      }

      if (initializedCount === 0) {
        return;
      }

      this.state.cascadeTomSelectInitialized = true;
      this._syncCascadeEnabledState();

      const firstItem = chain[0];
      const firstKey = this._getCascadeTomSelectKey(firstItem);
      const firstInstance = this.state.cascadeTomSelects[firstKey];
      if (firstInstance && typeof firstInstance.load === "function") {
        firstInstance.load("");
      }
    }

    _destroyCascadeTomSelects() {
      for (const instance of Object.values(this.state.cascadeTomSelects)) {
        if (instance && typeof instance.destroy === "function") {
          instance.destroy();
        }
      }
      this.state.cascadeTomSelects = {};
      this.state.cascadeTomSelectInitialized = false;
    }

    _getModalEl() {
      return (
        this.state.modalEl || document.getElementById("routeAnalysisRouteModal")
      );
    }

    _getSearchInputEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector("#routeAnalysisRouteSearchInput") : null;
    }

    _getRouteListEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="routeList"]') : null;
    }

    _getLoadingEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="loading"]') : null;
    }

    _getEmptyEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="empty"]') : null;
    }

    _getErrorsEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="errors"]') : null;
    }

    _getConfirmButtonEl() {
      const modal = this._getModalEl();
      return modal ? modal.querySelector('[data-route-analysis-route-picker-target="confirmButton"]') : null;
    }

    _updateRoutesTiming(count, elapsedMs) {
      const el = this.hasRoutesTimingTarget
        ? this.routesTimingTarget
        : this._getModalEl()
          ? this._getModalEl().querySelector(
              '[data-route-analysis-route-picker-target="routesTiming"]',
            )
          : null;
      if (!el) return;
      if (elapsedMs == null || elapsedMs === undefined) {
        el.style.display = "none";
        el.textContent = "";
        return;
      }
      const n = count != null ? count : 0;
      const suffix =
        this.state.routesHasNext && n > 0 ? " (есть ещё)" : "";
      el.textContent = `Показано ${n} маршрут(ов) за ${elapsedMs} мс${suffix}`;
      el.style.display = "";
    }

    _updateEqualizerVisibility(show) {
      if (this.hasEqualizerEmptyTarget) {
        setVisible(this.equalizerEmptyTarget, !show);
      }
      if (this.hasEqualizerControlsTarget) {
        setVisible(this.equalizerControlsTarget, show);
      }
    }

    _resetEqualizer() {
      this.state.equalizerBaseline = null;
      this.state.equalizerOverrides = {};
      clearTimeout(this.state.equalizerDebounceTimer);
      this._updateEqualizerVisibility(false);
      if (this.hasEqualizerPanelTarget) {
        this.equalizerPanelTarget.innerHTML = "";
      }
      if (this.hasEqualizerTypeSelectTarget) {
        this.equalizerTypeSelectTarget.innerHTML = "";
      }
    }

    _getVisibleEqualizerTypes() {
      const baseline = this.state.equalizerBaseline;
      if (!baseline || !Array.isArray(baseline.types)) return [];
      return baseline.types.filter((item) => item.visible !== false);
    }

    _getEqualizerTypeDef(typeKey) {
      const types = this._getVisibleEqualizerTypes();
      return types.find((item) => item.key === typeKey) || null;
    }

    _getEqualizerValue(typeKey, year) {
      const yearKey = String(year);
      const overrides = this.state.equalizerOverrides[typeKey];
      if (overrides && overrides[year] != null) {
        return Number(overrides[year]);
      }
      const typeDef = this._getEqualizerTypeDef(typeKey);
      if (!typeDef || !typeDef.values) return 0;
      const raw = typeDef.values[yearKey];
      const n = Number(String(raw).replace(",", "."));
      return Number.isFinite(n) ? n : 0;
    }

    _buildOverridesPayload() {
      const payload = {};
      for (const [typeKey, yearMap] of Object.entries(this.state.equalizerOverrides)) {
        if (!yearMap || typeof yearMap !== "object") continue;
        const out = {};
        for (const [year, value] of Object.entries(yearMap)) {
          if (value == null || Number.isNaN(Number(value))) continue;
          out[String(year)] = value;
        }
        if (Object.keys(out).length > 0) {
          payload[typeKey] = out;
        }
      }
      return Object.keys(payload).length > 0 ? payload : null;
    }

    _buildEqualizerTypeOptions() {
      if (!this.hasEqualizerTypeSelectTarget) return;
      const types = this._getVisibleEqualizerTypes();
      this.equalizerTypeSelectTarget.innerHTML = "";
      for (const typeDef of types) {
        const opt = document.createElement("option");
        opt.value = typeDef.key;
        opt.textContent = typeDef.label || typeDef.key;
        this.equalizerTypeSelectTarget.appendChild(opt);
      }
    }

    _renderEqualizerPanel() {
      if (!this.hasEqualizerPanelTarget) return;
      const scenario = this.state.selectedScenario;
      const startYear = scenario && scenario.start_year ? Number(scenario.start_year) : null;
      const endYear = scenario && scenario.end_year ? Number(scenario.end_year) : null;
      if (!startYear || !endYear) {
        this.equalizerPanelTarget.innerHTML = "";
        return;
      }

      const typeKey = this.hasEqualizerTypeSelectTarget
        ? this.equalizerTypeSelectTarget.value
        : null;
      const typeDef = typeKey ? this._getEqualizerTypeDef(typeKey) : null;
      if (!typeDef) {
        this.equalizerPanelTarget.innerHTML = "";
        return;
      }

      if (this.hasEqualizerUnitHintTarget) {
        this.equalizerUnitHintTarget.textContent = typeDef.unit
          ? `Единица: ${typeDef.unit}`
          : "";
      }

      if (typeDef.editable === false) {
        const notice =
          typeDef.notice ||
          "Настройка недоступна для текущего сценария.";
        this.equalizerPanelTarget.innerHTML = `
          <div class="alert alert-warning mb-0" role="status">
            ${escapeHtml(notice)}
          </div>
        `;
        return;
      }

      const step = Number(typeDef.step) || 1;
      const years = [];
      for (let y = startYear; y <= endYear; y += 1) years.push(y);

      const cols = years
        .map((year) => {
          const value = this._getEqualizerValue(typeKey, year);
          const max = value === 0 ? 1000 : value * 2;
          const min = 0;
          return `
            <div class="route-analysis-equalizer__year-col" data-year="${year}">
              <div class="route-analysis-equalizer__year-label">${escapeHtml(String(year))}</div>
              <input
                type="number"
                class="form-control form-control-sm route-analysis-equalizer__value-input"
                data-equalizer-input
                data-equalizer-type="${escapeHtml(typeKey)}"
                data-equalizer-year="${year}"
                value="${escapeHtml(String(value))}"
                step="${escapeHtml(String(step))}"
                min="${min}"
              />
              <div class="route-analysis-equalizer__slider-wrap">
                <input
                  type="range"
                  class="route-analysis-equalizer__slider"
                  data-equalizer-slider
                  data-equalizer-type="${escapeHtml(typeKey)}"
                  data-equalizer-year="${year}"
                  min="${min}"
                  max="${max}"
                  step="${escapeHtml(String(step))}"
                  value="${escapeHtml(String(value))}"
                />
              </div>
            </div>
          `;
        })
        .join("");

      this.equalizerPanelTarget.innerHTML = cols;

      const onInput = (event) => {
        const el = event.target;
        const t = el.getAttribute("data-equalizer-type");
        const y = Number(el.getAttribute("data-equalizer-year"));
        if (!t || Number.isNaN(y)) return;
        const num = Number(String(el.value).replace(",", "."));
        if (!Number.isFinite(num)) return;
        this._onEqualizerValueChange(t, y, num, el);
      };

      this.equalizerPanelTarget
        .querySelectorAll("[data-equalizer-input], [data-equalizer-slider]")
        .forEach((el) => {
          el.addEventListener("input", onInput);
        });
    }

    _onEqualizerValueChange(typeKey, year, value, sourceEl) {
      const col = sourceEl.closest("[data-year]");
      if (col) {
        const input = col.querySelector("[data-equalizer-input]");
        const slider = col.querySelector("[data-equalizer-slider]");
        if (input && input !== sourceEl) input.value = String(value);
        if (slider && slider !== sourceEl) {
          const max = value === 0 ? 1000 : value * 2;
          slider.max = String(max);
          slider.value = String(value);
        }
      }

      if (!this.state.equalizerOverrides[typeKey]) {
        this.state.equalizerOverrides[typeKey] = {};
      }
      this.state.equalizerOverrides[typeKey][year] = value;
      this._scheduleEqualizerRecalc();
    }

    _scheduleEqualizerRecalc() {
      clearTimeout(this.state.equalizerDebounceTimer);
      this.state.equalizerDebounceTimer = setTimeout(() => {
        this._recalculateWithOverrides();
      }, 250);
    }

    async _loadEqualizerBaseline() {
      if (!this.state.selectedRoute || !this.state.selectedScenarioId) {
        this._resetEqualizer();
        return;
      }

      const result = await this._loadRouteAnalysis({
        scenarioId: this.state.selectedScenarioId,
        routeId: this.state.selectedRoute.id,
      });
      if (!result.ok) {
        this._resetEqualizer();
        return;
      }

      this.state.equalizerBaseline = result.data.equalizer || null;
      this._buildEqualizerTypeOptions();
      this._updateEqualizerVisibility(true);
      this._renderEqualizerPanel();
    }

    async _recalculateWithOverrides() {
      if (!this.state.selectedRoute || !this.state.selectedScenarioId) return;
      if (this.state.equalizerRecalcInFlight) return;

      const overrides = this._buildOverridesPayload();
      if (!overrides) return;

      this.state.equalizerRecalcInFlight = true;
      try {
        const result = await this._loadRouteAnalysis({
          scenarioId: this.state.selectedScenarioId,
          routeId: this.state.selectedRoute.id,
          overrides,
          useCache: false,
        });
        if (result.ok) {
          await this._renderDiagram();
        }
      } finally {
        this.state.equalizerRecalcInFlight = false;
      }
    }

    async _loadRouteAnalysis({ scenarioId, routeId, overrides, useCache = true }) {
      if (!this.routeAnalysisUrlValue) {
        return { ok: false, errors: ["URL route_analysis не задан"] };
      }

      const overridesKey = overrides ? JSON.stringify(overrides) : "";
      const cacheKey = `${scenarioId}:${routeId}:${overridesKey}`;
      if (useCache && this.state.routeAnalysisCache.has(cacheKey)) {
        const cached = this.state.routeAnalysisCache.get(cacheKey);
        this.state.activeCalculateData = cached;
        return { ok: true, data: cached };
      }

      const body = {
        scenario_id: Number(scenarioId),
        route_id: Number(routeId),
      };
      if (overrides) {
        body.overrides = overrides;
      }

      const { data } = await fetchJson(this.routeAnalysisUrlValue, {
        method: "POST",
        body: JSON.stringify(body),
      });

      if (!data || !data.success) {
        return {
          ok: false,
          errors: (data && data.errors) || ["Ошибка расчёта структуры маршрута"],
        };
      }

      this.state.routeAnalysisCache.set(cacheKey, data);
      this.state.activeCalculateData = data;
      if (!overrides && data.equalizer) {
        this.state.equalizerBaseline = data.equalizer;
      }
      return { ok: true, data };
    }

    _rowValuesByKey(calculateData, rowKey) {
      if (!calculateData || !Array.isArray(calculateData.rows)) return null;
      const row = calculateData.rows.find((item) => item.key === rowKey);
      if (!row || !Array.isArray(row.values)) return null;
      return row.values.map((value) => {
        if (value != null && typeof value === "object" && value.rub != null) {
          return Number(String(value.rub).replace(",", "."));
        }
        return Number(String(value).replace(",", "."));
      });
    }

    _structurePartsForYearIndex(calculateData, yearIndex) {
      const toNum = (val) => {
        if (val == null) return null;
        const n = Number(String(val).replace(",", "."));
        return Number.isFinite(n) ? n : null;
      };

      const rowValuesByKey = (rowKey) => {
        if (!calculateData || !Array.isArray(calculateData.rows)) return null;
        const row = calculateData.rows.find((item) => item.key === rowKey);
        if (!row || !Array.isArray(row.values)) return null;
        const value = row.values[yearIndex];
        if (value != null && typeof value === "object" && value.rub != null) {
          return toNum(value.rub);
        }
        return toNum(value);
      };

      const price = rowValuesByKey("price_rub");
      const production = rowValuesByKey("cost");
      const rzd = rowValuesByKey("rzd");
      const ops = rowValuesByKey("operators");
      const trans = rowValuesByKey("transshipment");

      const base = price && price > 0 ? price : null;
      if (!base) return null;

      const clamp0 = (v) => (Number.isFinite(v) ? Math.max(v, 0) : 0);
      const round2 = (v) => Number(v.toFixed(2));
      const percentRaw = (v) => (v != null ? (v / base) * 100 : 0);

      const parts = [
        {
          name: "Себестоимость производства",
          valuePct: clamp0(percentRaw(production)),
          color: "#2da44e",
        },
        {
          name: 'Расходы ОАО "РЖД"',
          valuePct: clamp0(percentRaw(rzd)),
          color: "#8250df",
        },
        {
          name: "Расходы операторов",
          valuePct: clamp0(percentRaw(ops)),
          color: "#d29922",
        },
        {
          name: "Расходы на перевалку",
          valuePct: clamp0(percentRaw(trans)),
          color: "#bc4c00",
        },
      ];

      const sumKnown = [production, rzd, ops, trans].reduce(
        (acc, v) => (v != null ? acc + v : acc),
        0,
      );
      const marginPctRaw = ((base - sumKnown) / base) * 100;
      const marginPctNonNeg = clamp0(marginPctRaw);
      const usedRaw = parts.reduce((acc, p) => acc + p.valuePct, 0);
      const totalRaw = usedRaw + marginPctNonNeg;
      if (!totalRaw) return null;

      const scale = 100 / totalRaw;
      for (const p of parts) {
        p.valuePct = round2(p.valuePct * scale);
      }

      const marginPart = {
        name: "Маржинальность холдинга",
        valuePct: round2(marginPctNonNeg * scale),
        color: "#cf222e",
      };
      const usedRounded = parts.reduce((acc, p) => acc + p.valuePct, 0);
      marginPart.valuePct = round2(100 - usedRounded);
      if (marginPart.valuePct < 0) marginPart.valuePct = 0;
      parts.push(marginPart);
      return parts;
    }

    _formatMoney(val) {
      const n = Number(String(val).replace(",", "."));
      if (!Number.isFinite(n)) return "—";
      return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 0 }).format(
        Math.round(n),
      );
    }

    _formatMlnTonsDelta(val) {
      const n = Number(String(val).replace(",", "."));
      if (!Number.isFinite(n)) return "—";
      const absFormatted = new Intl.NumberFormat("ru-RU", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }).format(Math.abs(n));
      if (n > 0) return `+${absFormatted}`;
      if (n < 0) return `-${absFormatted}`;
      return absFormatted;
    }

    _formatPct(val) {
      const n = Number(String(val).replace(",", "."));
      if (!Number.isFinite(n)) return "0.00";
      return n.toFixed(2);
    }

    _hideDiagramExtras() {
      const tsEl = document.getElementById("routeAnalysisTsAnnotations");
      if (tsEl) {
        tsEl.style.display = "none";
        tsEl.innerHTML = "";
      }
      const effectsEl = document.getElementById("routeAnalysisEffectsTableWrap");
      if (effectsEl) {
        effectsEl.style.display = "none";
        effectsEl.innerHTML = "";
      }
      const kpiEl = document.getElementById("routeAnalysisKpiWrap");
      if (kpiEl) {
        kpiEl.style.display = "none";
        kpiEl.innerHTML = "";
      }
    }

    _fakeGdfTr(yearRows) {
      const partCh = 0.2;
      return yearRows.map((row) => {
        const next = { ...row };
        const tail = next.costs * partCh;
        const keys = ["transport", "marginality"];
        const nonZero = keys.filter((key) => next[key] !== 0);
        if (nonZero.length > 0) {
          const add = Math.round((tail / nonZero.length) * 100) / 100;
          for (const key of keys) {
            if (next[key] !== 0) next[key] += add;
          }
        }
        next.costs *= 1 - partCh;
        return next;
      });
    }

    _rowRubByKey(calculateData, rowKey, yearIndex) {
      if (!calculateData || !Array.isArray(calculateData.rows)) return 0;
      const row = calculateData.rows.find((item) => item.key === rowKey);
      if (!row || !Array.isArray(row.values)) return 0;
      const value = row.values[yearIndex];
      if (value != null && typeof value === "object" && value.rub != null) {
        const n = Number(String(value.rub).replace(",", "."));
        return Number.isFinite(n) ? n : 0;
      }
      const n = Number(String(value).replace(",", "."));
      return Number.isFinite(n) ? n : 0;
    }

    _mapYearValues(mapByYear, years) {
      if (!mapByYear) return years.map(() => 0);
      return years.map((year) => {
        const raw = mapByYear[String(year)];
        const n = Number(String(raw).replace(",", "."));
        return Number.isFinite(n) ? n : 0;
      });
    }

    async _fetchRouteAnalysisData({ loadingMessage }) {
      const scenarioId = this.state.selectedScenarioId;
      const routeId = this.state.selectedRoute ? this.state.selectedRoute.id : null;
      if (!scenarioId || !routeId) {
        return { ok: false, errors: ["Не удалось определить сценарий и маршрут"] };
      }
      try {
        const result = await this._loadRouteAnalysis({
          scenarioId,
          routeId,
          overrides: this._buildOverridesPayload(),
        });
        return result;
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("[route-analysis] route_analysis failed", e);
        return { ok: false, errors: ["Ошибка расчёта (см. консоль)"] };
      }
    }

    _renderTsAnnotations(years, transportStructure) {
      const el = document.getElementById("routeAnalysisTsAnnotations");
      if (!el || !transportStructure) return;
      const transportPct = transportStructure.transport_pct_by_year || {};
      const marginPct = transportStructure.marginality_pct_by_year || {};
      el.innerHTML = years
        .map((year) => {
          const transport = transportPct[String(year)] ?? "0";
          const margin = marginPct[String(year)] ?? "0";
          return `
            <div class="route-analysis-ts-annotations__year">
              <div class="route-analysis-ts-annotations__year-label">${escapeHtml(String(year))}</div>
              <span class="route-analysis-ts-annotations__badge route-analysis-ts-annotations__badge--transport">
                ${escapeHtml(transport)}%
              </span>
              <span class="route-analysis-ts-annotations__badge route-analysis-ts-annotations__badge--margin">
                ${escapeHtml(margin)}%
              </span>
            </div>
          `;
        })
        .join("");
      el.style.display = years.length ? "" : "none";
    }

    _renderEffectsTable(containerEl, data) {
      if (!containerEl) return;
      const years = Array.isArray(data.years) ? data.years : [];
      const rows = data.effects && Array.isArray(data.effects.rows) ? data.effects.rows : [];
      if (!years.length || !rows.length) {
        containerEl.innerHTML = `
          <div class="text-center text-muted py-4">Нет данных для таблицы эффектов.</div>
        `;
        return;
      }

      const thYears = years
        .map((y) => `<th class="text-end">${escapeHtml(String(y))}</th>`)
        .join("");

      const renderCell = (cell) => {
        if (!cell) return `<td class="text-end">—</td>`;
        const rub = cell.rub != null ? cell.rub : "0";
        const pctNum = Number(String(cell.pct).replace(",", "."));
        const pctStr = this._formatPct(cell.pct);
        const pctClass =
          Number.isFinite(pctNum) && pctNum < 0 ? "text-danger" : "";
        const pctPrefix = Number.isFinite(pctNum) && pctNum > 0 ? "+" : "";
        return `
          <td class="text-end ${pctClass}">
            ${escapeHtml(rub)}<br />
            <span class="${pctClass}">(${escapeHtml(pctPrefix + pctStr)}%)</span>
          </td>
        `;
      };

      const tbody = rows
        .map((row) => {
          const values = row.values || {};
          const cells = years.map((y) => renderCell(values[String(y)])).join("");
          return `
            <tr>
              <td class="text-muted">${escapeHtml(row.label || row.key || "")}</td>
              ${cells}
            </tr>
          `;
        })
        .join("");

      containerEl.innerHTML = `
        <div class="table-responsive">
          <table class="table table-sm table-vcenter">
            <thead>
              <tr>
                <th>Показатель</th>
                ${thYears}
              </tr>
            </thead>
            <tbody>${tbody}</tbody>
          </table>
        </div>
      `;
    }

    _renderKpiMetric(metric) {
      if (!metric) return "";
      const isRetentionCoefficient = String(metric.label || "").includes(
        "Коэффициент сохранения",
      );
      const isMarginality = String(metric.label || "").includes("Маржинальность");
      const pctNum = Number(String(metric.pct ?? "").replace(",", "."));
      const pctClass =
        isMarginality && Number.isFinite(pctNum) && pctNum < 0
          ? "text-danger"
          : "";
      const rub =
        metric.rub != null && metric.rub !== ""
          ? isRetentionCoefficient
            ? `(${this._formatMlnTonsDelta(metric.rub)} млн т)`
            : `${this._formatMoney(metric.rub)} руб.`
          : "—";
      const pct =
        metric.pct != null && metric.pct !== ""
          ? isRetentionCoefficient
            ? this._formatPct(metric.pct)
            : `${this._formatPct(metric.pct)}%`
          : "—";
      return `
        <div class="route-analysis-kpi-metric">
          <div class="route-analysis-kpi-metric__row">
            <span class="route-analysis-kpi-metric__pct ${pctClass}">${escapeHtml(pct)}</span>
            <span class="route-analysis-kpi-metric__rub">${escapeHtml(rub)}</span>
          </div>
          <div class="route-analysis-kpi-metric__label">${escapeHtml(metric.label || "")}</div>
        </div>
      `;
    }

    _renderRzdTariffSensitivityChart(ctx, points) {
      if (!ctx || !points || !points.length) return;

      if (this.state.trendsChart) {
        try {
          this.state.trendsChart.destroy();
        } catch (_e) {
          // ignore
        }
        this.state.trendsChart = null;
      }

      const labels = points.map((point) => String(point.change_pct));
      const zeroIndex = points.findIndex((point) => String(point.change_pct) === "0");
      const coefficientData = points.map((point) => {
        const value = Number(String(point.coefficient ?? "").replace(",", "."));
        return Number.isFinite(value) ? value : null;
      });

      this.state.trendsChart = new window.Chart(ctx, {
        type: "line",
        data: {
          labels,
          datasets: [
            {
              label: "Коэффициент сохранения грузовой базы",
              data: coefficientData,
              borderColor: "#1f6feb",
              backgroundColor: "#1f6feb",
              borderWidth: 2,
              pointRadius: coefficientData.map((_value, index) =>
                index === zeroIndex ? 6 : 2,
              ),
              pointHoverRadius: coefficientData.map((_value, index) =>
                index === zeroIndex ? 7 : 4,
              ),
              tension: 0,
            },
            {
              label: "Без изменения объёма",
              data: labels.map(() => 1),
              borderColor: "#9ca3af",
              backgroundColor: "#9ca3af",
              borderWidth: 2,
              borderDash: [6, 4],
              pointRadius: 0,
              pointHoverRadius: 0,
              fill: false,
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: {
            legend: {
              position: "bottom",
              labels: {
                boxWidth: 18,
                boxHeight: 10,
              },
            },
            title: {
              display: true,
              text: 'Изменение тарифа ОАО "РЖД"',
              align: "start",
              font: { size: 16, weight: "600" },
              padding: { bottom: 12 },
            },
            datalabels: {
              display: false,
            },
            tooltip: {
              enabled: true,
              mode: "index",
              intersect: false,
              callbacks: {
                label: (context) => {
                  const label = context.dataset.label || "";
                  const value = context.parsed.y;
                  if (value == null || Number.isNaN(value)) {
                    return `${label}: —`;
                  }
                  return `${label}: ${value.toFixed(4)}`;
                },
              },
            },
          },
          interaction: {
            mode: "index",
            intersect: false,
          },
          scales: {
            x: {
              title: {
                display: true,
                text: 'Изменение тарифа ОАО "РЖД", %',
              },
              grid: { display: false },
              ticks: {
                maxTicksLimit: 11,
                autoSkip: true,
              },
            },
            y: {
              title: {
                display: true,
                text: "Коэффициент сохранения грузовой базы",
              },
              grid: { color: "#e5e7eb" },
            },
          },
        },
      });
    }

    _renderKpiCards(containerEl, data) {
      if (!containerEl) return;
      const items = data.kpi && Array.isArray(data.kpi.by_year) ? data.kpi.by_year : [];
      if (!items.length) {
        containerEl.innerHTML = `
          <div class="text-center text-muted py-4 w-100">Нет KPI для отображения.</div>
        `;
        return;
      }

      containerEl.innerHTML = items
        .map((item) => {
          const metrics = [
            item.transport,
            item.rzd,
            item.marginality,
            item.elasticity,
          ]
            .filter(Boolean)
            .map((metric) => this._renderKpiMetric(metric))
            .join("");
          return `
            <div class="route-analysis-kpi-card">
              <div class="route-analysis-kpi-card__title">${escapeHtml(String(item.year))} год</div>
              ${metrics}
            </div>
          `;
        })
        .join("");
    }

    async _renderStructureTable({ scenarioId, routeId, containerEl }) {
      if (!containerEl) return;

      containerEl.innerHTML = `
        <div class="text-center text-muted py-4">
          <div class="spinner-border text-primary" role="status" aria-label="Загрузка"></div>
          <div class="mt-2">Расчёт таблицы…</div>
        </div>
      `;

      let result;
      try {
        result = await this._loadRouteAnalysis({
          scenarioId,
          routeId,
          overrides: this._buildOverridesPayload(),
        });
      } catch (e) {
        // eslint-disable-next-line no-console
        console.error("[route-analysis] route_analysis failed", e);
        containerEl.innerHTML = `
          <div class="alert alert-danger" role="alert">
            Ошибка расчёта таблицы (см. консоль).
          </div>
        `;
        return;
      }

      if (!result.ok) {
        containerEl.innerHTML = `
          <div class="alert alert-danger" role="alert">
            ${escapeHtml((result.errors || ["Ошибка"]).join("; "))}
          </div>
        `;
        return;
      }

      const data = result.data;
      const years = Array.isArray(data.years) ? data.years : [];
      const rows = Array.isArray(data.rows) ? data.rows : [];

      if (years.length === 0 || rows.length === 0) {
        containerEl.innerHTML = `
          <div class="text-center text-muted py-4">
            Нет данных для отображения таблицы.
          </div>
        `;
        return;
      }

      const thYears = years
        .map((y) => `<th class="text-end">${escapeHtml(String(y))}</th>`)
        .join("");

      const renderCell = (row, value) => {
        if (row.format === "marginality") {
          const rubRaw = value && value.rub != null ? value.rub : 0;
          const pctRaw = value && value.pct != null ? value.pct : 0;
          const rub = Number(String(rubRaw).replace(",", "."));
          const cls =
            Number.isFinite(rub) && rub < 0
              ? "text-danger"
              : Number.isFinite(rub) && rub > 0
                ? "text-success"
                : "";
          const rubStr = this._formatMoney(rubRaw);
          const pctStr = this._formatPct(pctRaw);
          return `<td class="text-end ${cls}">${escapeHtml(rubStr)} (${escapeHtml(pctStr)}%)</td>`;
        }

        const money = this._formatMoney(value);
        return `<td class="text-end">${escapeHtml(money)}</td>`;
      };

      const tbody = rows
        .map((row) => {
          const values = Array.isArray(row.values) ? row.values : [];
          const cells = years
            .map((_y, idx) => renderCell(row, values[idx]))
            .join("");
          return `
            <tr>
              <td class="text-muted">${escapeHtml(row.label || row.key || "")}</td>
              ${cells}
            </tr>
          `;
        })
        .join("");

      containerEl.innerHTML = `
        <div class="table-responsive">
          <table class="table table-sm table-vcenter">
            <thead>
              <tr>
                <th>Параметр</th>
                ${thYears}
              </tr>
            </thead>
            <tbody>
              ${tbody}
            </tbody>
          </table>
        </div>
      `;
    }
  }

  application.register(
    "route-analysis-route-picker",
    RouteAnalysisRoutePickerController,
  );
})();

