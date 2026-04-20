import { fetchJson } from "../lib/http.js";
import { escapeHtml, setVisible } from "../lib/dom.js";
import { renderErrors } from "../lib/errors.js";
import { renderPagination } from "../lib/pagination.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for routes.");
    return;
  }

  class RoutesController extends Stimulus.Controller {
    static targets = [
      "routeSetSelect",
      "cargoSelect",
      "originStationSelect",
      "destinationStationSelect",
      "routeSummary",
      "routesTableBody",
      "routesSummary",
      "routesPagination",
      "routesLoading",
      "routesEmpty",
      "routesPageSize",
      "routesSearchQuery",
      "routeSetErrors",
      "routeErrors",
    ];

    static values = {
      routeSetListUrl: String,
      routeSetDetailUrlTemplate: String,
      routeSetCreateUrl: String,
      routeSetUpdateUrlTemplate: String,
      routeSetDeleteUrlTemplate: String,
      routeListUrl: String,
      routeDetailUrlTemplate: String,
      routeCreateUrl: String,
      routeUpdateUrlTemplate: String,
      routeDeleteUrlTemplate: String,
      cargoSearchUrl: String,
      stationSearchUrl: String,
      pageSizeDefault: { type: Number, default: 20 },
    };

    connect() {
      this.state = {
        routeSetId: null,
        page: 1,
        pageSize: this.pageSizeDefaultValue || 20,
        totalPages: 1,
      };
      this.searchDebounceTimer = null;
      this.cargoSelectInstance = null;
      this.initCargoSelect();
      this.originStationSelectInstance = null;
      this.destinationStationSelectInstance = null;
      this.initStationSelects();
      this.summaryState = {
        origin: null,
        destination: null,
        messageType: null,
      };
      this.initMessageTypeSummary();
      this.updateSummaryView();
      this.loadRouteSets();
    }

    // === Actions ===
    onRouteSetChange(event) {
      const val = event.currentTarget.value;
      this.state.routeSetId = val ? parseInt(val, 10) : null;
      this.loadRoutes(1);
    }

    onPageSizeChange() {
      this.loadRoutes(1);
    }

    onSearchInput() {
      if (this.searchDebounceTimer) {
        clearTimeout(this.searchDebounceTimer);
      }
      this.searchDebounceTimer = setTimeout(() => {
        this.loadRoutes(1);
      }, 400);
    }

    applyFilters() {
      this.loadRoutes(1);
    }

    resetFilters() {
      if (this.hasRoutesSearchQueryTarget) {
        this.routesSearchQueryTarget.value = "";
      }
      if (this.hasRoutesPageSizeTarget) {
        this.routesPageSizeTarget.value = String(this.pageSizeDefaultValue || 20);
      }
      this.loadRoutes(1);
    }

    openRouteSetCreate() {
      this.showRouteSetModal("create");
    }

    openRouteSetEdit() {
      this.showRouteSetModal("edit");
    }

    async submitRouteSet() {
      const idInput = document.getElementById("routeSetId");
      const nameInput = document.getElementById("routeSetName");
      const codeInput = document.getElementById("routeSetCode");

      const id = idInput.value;
      const payload = {
        name: nameInput.value.trim(),
        code: codeInput.value.trim(),
      };

      const isCreate = !id;
      const url = isCreate
        ? this.routeSetCreateUrlValue
        : this.routeSetUpdateUrlTemplateValue.replace(
            "0",
            encodeURIComponent(id),
          );

      const { data } = await fetchJson(url, { method: "POST", body: payload });
      if (!data || !data.success) {
        renderErrors(
          this.routeSetErrorsTarget,
          (data && data.errors) || ["Ошибка сохранения набора"],
        );
        return;
      }

      renderErrors(this.routeSetErrorsTarget, []);
      const modalEl = document.getElementById("routeSetModal");
      const modal = bootstrap.Modal.getInstance(modalEl);
      if (modal) modal.hide();
      if (data.item && data.item.id) {
        this.state.routeSetId = data.item.id;
      }
      this.loadRouteSets();
    }

    async deleteRouteSet() {
      const select = this.routeSetSelectTarget;
      const selectedId = select.value;
      if (!selectedId) {
        window.alert("Сначала выберите набор маршрутов");
        return;
      }
      if (
        !window.confirm(
          "Вы действительно хотите удалить этот набор маршрутов вместе со всеми маршрутами?",
        )
      ) {
        return;
      }
      const url = this.routeSetDeleteUrlTemplateValue.replace(
        "0",
        encodeURIComponent(selectedId),
      );
      const { data } = await fetchJson(url, { method: "POST", body: null });
      if (!data || !data.success) {
        window.alert(
          ((data && data.errors) || ["Ошибка удаления набора"]).join("\n"),
        );
        return;
      }
      this.state.routeSetId = null;
      this.loadRouteSets();
    }

    openRouteCreate() {
      this.showRouteModal("create");
    }

    openRouteEdit(event) {
      const id = event.currentTarget.dataset.id;
      this.showRouteModal("edit", id);
    }

    async submitRoute() {
      if (!this.state.routeSetId) {
        window.alert("Сначала выберите набор маршрутов");
        return;
      }
      const id = document.getElementById("routeId").value;
      const isCreate = !id;
      const url = isCreate
        ? this.routeCreateUrlValue
        : this.routeUpdateUrlTemplateValue.replace(
            "0",
            encodeURIComponent(id),
          );
      const payload = this.collectRoutePayload();

      const { data } = await fetchJson(url, { method: "POST", body: payload });
      if (!data || !data.success) {
        renderErrors(
          this.routeErrorsTarget,
          (data && data.errors) || ["Ошибка сохранения маршрута"],
        );
        return;
      }

      renderErrors(this.routeErrorsTarget, []);
      const modalEl = document.getElementById("routeModal");
      const modal = bootstrap.Modal.getInstance(modalEl);
      if (modal) modal.hide();
      this.loadRoutes(isCreate ? 1 : this.state.page);
    }

    async deleteRoute(event) {
      const id = event.currentTarget.dataset.id;
      if (!id) return;
      if (
        !window.confirm(
          "Вы действительно хотите удалить этот маршрут?",
        )
      ) {
        return;
      }
      const url = this.routeDeleteUrlTemplateValue.replace(
        "0",
        encodeURIComponent(id),
      );
      const { data } = await fetchJson(url, { method: "POST", body: null });
      if (!data || !data.success) {
        window.alert(
          ((data && data.errors) || ["Ошибка удаления маршрута"]).join("\n"),
        );
        return;
      }
      this.loadRoutes(this.state.page);
    }

    // === Tom Select для выбора груза ===
    initCargoSelect() {
      if (!this.hasCargoSelectTarget) return;
      if (typeof TomSelect === "undefined") {
        console.warn("TomSelect is not available on window.TomSelect");
        return;
      }

      const searchUrl = this.cargoSearchUrlValue;
      if (!searchUrl) {
        console.warn("cargoSearchUrlValue is not defined for routes controller");
        return;
      }

      const selectEl = this.cargoSelectTarget;

      this.cargoSelectInstance = new TomSelect(selectEl, {
        valueField: "value",
        labelField: "text",
        searchField: ["text"],
        maxOptions: 50,
        allowEmptyOption: true,
        loadThrottle: 400,
        preload: false,
        render: {
          option(item, escape) {
            return `<div>${escape(item.text || "")}</div>`;
          },
          item(item, escape) {
            return `<div>${escape(item.text || "")}</div>`;
          },
        },
        load: async (query, callback) => {
          const q = (query || "").trim();
          if (q.length < 2) {
            return callback();
          }
          try {
            const params = new URLSearchParams();
            params.set("page", "1");
            params.set("page_size", "20");
            params.set("search", q);
            const { data } = await fetchJson(
              `${searchUrl}?${params.toString()}`,
              { method: "GET" },
            );
            if (!data || !data.success || !Array.isArray(data.items)) {
              return callback();
            }
            const options = data.items.map((item) => ({
              value: String(item.code),
              text: `${item.code} — ${item.name}`,
            }));
            callback(options);
          } catch (e) {
            console.error("Ошибка загрузки грузов для Tom Select:", e);
            callback();
          }
        },
      });
    }

    // === Tom Select для выбора станций ===
    initStationSelects() {
      if (typeof TomSelect === "undefined") {
        console.warn("TomSelect is not available on window.TomSelect (stations)");
        return;
      }

      const searchUrl = this.stationSearchUrlValue;
      if (!searchUrl) {
        console.warn("stationSearchUrlValue is not defined for routes controller");
        return;
      }

      this.stationCache = this.stationCache || {};

      const makeConfig = (role) => ({
        valueField: "value",
        labelField: "text",
        searchField: ["text"],
        maxOptions: 50,
        allowEmptyOption: true,
        loadThrottle: 400,
        preload: false,
        render: {
          option(item, escape) {
            return `<div>${escape(item.text || "")}</div>`;
          },
          item(item, escape) {
            return `<div>${escape(item.text || "")}</div>`;
          },
        },
        load: async (query, callback) => {
          const q = (query || "").trim();
          if (q.length < 2) {
            return callback();
          }
          try {
            const params = new URLSearchParams();
            params.set("page", "1");
            params.set("page_size", "20");
            params.set("search", q);
            const { data } = await fetchJson(
              `${searchUrl}?${params.toString()}`,
              { method: "GET" },
            );
            if (!data || !data.success || !Array.isArray(data.items)) {
              return callback();
            }
            data.items.forEach((st) => {
              const key = String(st.esr_code);
              this.stationCache[key] = st;
            });
            const options = data.items.map((st) => ({
              value: String(st.esr_code),
              text: `${st.esr_code} — ${st.short_name || st.full_name || ""}`,
            }));
            callback(options);
          } catch (e) {
            console.error("Ошибка загрузки станций для Tom Select:", e);
            callback();
          }
        },
        onChange: (value) => {
          const key = value ? String(value) : "";
          const st =
            key && this.stationCache ? this.stationCache[key] : null;
          if (role === "origin") {
            this.summaryState.origin = st;
          } else if (role === "destination") {
            this.summaryState.destination = st;
          }
          this.updateSummaryView();
        },
      });

      if (this.hasOriginStationSelectTarget) {
        this.originStationSelectInstance = new TomSelect(
          this.originStationSelectTarget,
          makeConfig("origin"),
        );
      }
      if (this.hasDestinationStationSelectTarget) {
        this.destinationStationSelectInstance = new TomSelect(
          this.destinationStationSelectTarget,
          makeConfig("destination"),
        );
      }
    }

    initMessageTypeSummary() {
      const select = document.getElementById("routeMessageTypeId");
      if (!select) return;
      select.addEventListener("change", () => {
        const opt = select.options[select.selectedIndex];
        if (!opt || !opt.value) {
          this.summaryState.messageType = null;
        } else {
          this.summaryState.messageType = {
            id: opt.value,
            name: (opt.textContent || "").trim(),
            direction: opt.dataset.direction || null,
          };
        }
        this.updateSummaryView();
      });
    }

    updateSummaryView() {
      if (!this.hasRouteSummaryTarget) return;
      const origin = this.summaryState.origin;
      const destination = this.summaryState.destination;
      const mt = this.summaryState.messageType;

      const formatStation = (st) => {
        if (!st) return "не выбрано";
        const name = st.full_name || st.short_name || "";
        const parts = [];
        if (st.region_full_name) {
          parts.push(st.region_full_name);
        }
        const rr = st.railroad_name || st.railroad_code;
        if (rr) {
          const dir = st.railroad_direction;
          if (dir) {
            parts.push(`${rr} (${dir})`);
          } else {
            parts.push(rr);
          }
        }
        if (!parts.length) return name || "не выбрано";
        return `${name} — ${parts.join(", ")}`;
      };

      const originText = formatStation(origin);
      const destText = formatStation(destination);
      let mtText = "не выбрано";
      if (mt && mt.name) {
        mtText = mt.name;
        if (mt.direction) {
          mtText += ` (${mt.direction})`;
        }
      }

      this.routeSummaryTarget.innerHTML = `
        <div><strong>Отправление:</strong> ${escapeHtml(originText)}</div>
        <div><strong>Назначение:</strong> ${escapeHtml(destText)}</div>
        <div><strong>Тип сообщения:</strong> ${escapeHtml(mtText)}</div>
      `;
    }

    // === Наборы маршрутов ===
    async loadRouteSets() {
      const select = this.routeSetSelectTarget;
      select.innerHTML = '<option value="">Загрузка...</option>';

      const url = this.routeSetListUrlValue;
      const { data } = await fetchJson(
        url + "?page=1&page_size=1000",
        { method: "GET" },
      );
      if (!data || !data.success) {
        const errors =
          (data && data.errors) || ["Ошибка загрузки наборов маршрутов"];
        window.alert(errors.join("\n"));
        return;
      }

      const items = data.items || [];
      if (!items.length) {
        select.innerHTML = '<option value="">Нет наборов</option>';
        this.state.routeSetId = null;
        this.loadRoutes(1);
        return;
      }

      select.innerHTML = items
        .map(
          (it) =>
            `<option value="${it.id}">${escapeHtml(it.code || "")} — ${escapeHtml(
              it.name || "",
            )}</option>`,
        )
        .join("");

      if (!this.state.routeSetId) {
        this.state.routeSetId = items[0].id;
      }
      select.value = String(this.state.routeSetId);
      this.loadRoutes(1);
    }

    // === Маршруты ===
    buildRoutesParams() {
      const params = new URLSearchParams();
      params.set("page", String(this.state.page));

      const pageSize =
        (this.hasRoutesPageSizeTarget &&
          parseInt(this.routesPageSizeTarget.value || "20", 10)) ||
        this.pageSizeDefaultValue ||
        20;
      this.state.pageSize = pageSize;
      params.set("page_size", String(pageSize));
      params.set("route_set_id", String(this.state.routeSetId || ""));

      if (this.hasRoutesSearchQueryTarget) {
        const search = this.routesSearchQueryTarget.value.trim();
        if (search) params.set("search", search);
      }

      return params;
    }

    async loadRoutes(page) {
      if (!this.state.routeSetId) {
        if (this.hasRoutesTableBodyTarget) {
          this.routesTableBodyTarget.innerHTML = "";
        }
        if (this.hasRoutesEmptyTarget) {
          setVisible(this.routesEmptyTarget, true);
        }
        this.updateRoutesSummary(0);
        if (this.hasRoutesPaginationTarget) {
          this.routesPaginationTarget.innerHTML = "";
        }
        return;
      }

      if (page) this.state.page = page;
      const params = this.buildRoutesParams();

      if (this.hasRoutesLoadingTarget) {
        setVisible(this.routesLoadingTarget, true);
      }
      if (this.hasRoutesEmptyTarget) {
        setVisible(this.routesEmptyTarget, false);
      }
      if (this.hasRoutesTableBodyTarget) {
        this.routesTableBodyTarget.innerHTML = "";
      }

      const url = this.routeListUrlValue;
      const { data } = await fetchJson(
        url + "?" + params.toString(),
        { method: "GET" },
      );

      if (this.hasRoutesLoadingTarget) {
        setVisible(this.routesLoadingTarget, false);
      }

      const tbody = this.hasRoutesTableBodyTarget
        ? this.routesTableBodyTarget
        : null;
      const empty = this.hasRoutesEmptyTarget ? this.routesEmptyTarget : null;

      if (!tbody || !empty) return;

      if (!data || !data.success) {
        tbody.innerHTML =
          '<tr><td colspan="11"><div class="alert alert-danger mb-0">' +
          escapeHtml(
            ((data && data.errors) || ["Ошибка загрузки"]).join(", "),
          ) +
          "</div></td></tr>";
        return;
      }

      const items = data.items || [];
      if (!items.length) {
        tbody.innerHTML = "";
        setVisible(empty, true);
      } else {
        setVisible(empty, false);
        tbody.innerHTML = items.map((it) => this.createRouteRow(it)).join("");
      }

      this.state.page = data.page || 1;
      this.state.totalPages = data.total_pages || 1;
      this.updateRoutesSummary(data.total || 0);
      this.updateRoutesPagination();
    }

    createRouteRow(item) {
      const cargo =
        (item.cargo_code ? escapeHtml(String(item.cargo_code)) : "") +
        (item.cargo_name ? " — " + escapeHtml(item.cargo_name) : "");
      const origin =
        (item.origin_esr_code != null
          ? escapeHtml(String(item.origin_esr_code))
          : "") +
        (item.origin_station_name
          ? " — " + escapeHtml(item.origin_station_name)
          : "");
      const dest =
        (item.destination_esr_code != null
          ? escapeHtml(String(item.destination_esr_code))
          : "") +
        (item.destination_station_name
          ? " — " + escapeHtml(item.destination_station_name)
          : "");
      const transport =
        item.transport_total_cost_per_ton != null
          ? escapeHtml(String(item.transport_total_cost_per_ton))
          : "—";
      const market =
        item.market_price_per_ton != null
          ? escapeHtml(String(item.market_price_per_ton))
          : "—";

      return `
        <tr data-id="${item.id}">
          <td>${cargo}</td>
          <td>${origin}</td>
          <td>${dest}</td>
          <td>${escapeHtml(item.message_type_name || "")}</td>
          <td>${escapeHtml(item.route_code || "")}</td>
          <td>${escapeHtml(item.wagon_kind_name || "")}</td>
          <td>${escapeHtml(item.shipment_type_name || "")}</td>
          <td>${transport}</td>
          <td>${market}</td>
          <td class="text-end">
            <div class="btn-group" role="group" aria-label="Действия">
              <button
                type="button"
                class="btn btn-sm btn-outline-primary"
                data-id="${item.id}"
                data-action="click->routes#openRouteEdit"
                title="Редактировать"
              >
                <i class="ti ti-edit"></i>
              </button>
              <button
                type="button"
                class="btn btn-sm btn-outline-danger"
                data-id="${item.id}"
                data-action="click->routes#deleteRoute"
                title="Удалить"
              >
                <i class="ti ti-trash"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    }

    updateRoutesSummary(total) {
      if (!this.hasRoutesSummaryTarget) return;
      const from = (this.state.page - 1) * this.state.pageSize + 1;
      const to = Math.min(this.state.page * this.state.pageSize, total || 0);
      this.routesSummaryTarget.textContent = total
        ? `Показаны ${from}–${to} из ${total} маршрутов`
        : "Нет маршрутов";
    }

    updateRoutesPagination() {
      if (!this.hasRoutesPaginationTarget) return;
      renderPagination(this.routesPaginationTarget, {
        page: this.state.page,
        totalPages: this.state.totalPages,
        onPage: (p) => this.loadRoutes(p),
      });
    }

    // === Модалки ===
    async showRouteSetModal(mode) {
      const modalEl = document.getElementById("routeSetModal");
      const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
      const titleEl = document.getElementById("routeSetModalTitle");
      const idInput = document.getElementById("routeSetId");
      const nameInput = document.getElementById("routeSetName");
      const codeInput = document.getElementById("routeSetCode");

      renderErrors(this.routeSetErrorsTarget, []);

      if (mode === "create") {
        titleEl.textContent = "Создать набор маршрутов";
        idInput.value = "";
        nameInput.value = "";
        codeInput.value = "";
        modal.show();
        return;
      }

      const select = this.routeSetSelectTarget;
      const selectedId = select.value;
      if (!selectedId) {
        window.alert("Сначала выберите набор маршрутов");
        return;
      }

      const url = this.routeSetDetailUrlTemplateValue.replace(
        "0",
        encodeURIComponent(selectedId),
      );
      const { data } = await fetchJson(url, { method: "GET" });
      if (!data || !data.success || !data.item) {
        renderErrors(
          this.routeSetErrorsTarget,
          (data && data.errors) || ["Не удалось загрузить набор"],
        );
        return;
      }

      const it = data.item;
      titleEl.textContent = "Редактировать набор маршрутов";
      idInput.value = it.id;
      nameInput.value = it.name || "";
      codeInput.value = it.code || "";
      modal.show();
    }

    async showRouteModal(mode, id) {
      const modalEl = document.getElementById("routeModal");
      const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
      const titleEl = document.getElementById("routeModalTitle");
      const form = document.getElementById("routeForm");
      form.reset();
      document.getElementById("routeId").value = mode === "edit" ? id : "";
      renderErrors(this.routeErrorsTarget, []);

      const openFirstAccordionSection = () => {
        const first = document.getElementById("routeAccCollapse1");
        if (!first) return;
        try {
          new bootstrap.Collapse(first, { toggle: true });
        } catch (e) {
          console.warn("Не удалось раскрыть секцию аккордиона:", e);
        }
      };

      if (mode === "create") {
        if (!this.state.routeSetId) {
          window.alert("Сначала выберите набор маршрутов");
          return;
        }
        titleEl.textContent = "Создать маршрут";
        if (this.cargoSelectInstance) {
          this.cargoSelectInstance.clear(true);
        }
        if (this.originStationSelectInstance) {
          this.originStationSelectInstance.clear(true);
        }
        if (this.destinationStationSelectInstance) {
          this.destinationStationSelectInstance.clear(true);
        }
        this.summaryState.origin = null;
        this.summaryState.destination = null;
        this.summaryState.messageType = null;
        this.updateSummaryView();
        modal.show();
        openFirstAccordionSection();
        return;
      }

      titleEl.textContent = "Редактировать маршрут";
      const url = this.routeDetailUrlTemplateValue.replace(
        "0",
        encodeURIComponent(id),
      );
      const { data } = await fetchJson(url, { method: "GET" });
      if (!data || !data.success || !data.item) {
        renderErrors(
          this.routeErrorsTarget,
          (data && data.errors) || ["Не удалось загрузить маршрут"],
        );
        return;
      }

      const it = data.item;
      if (this.cargoSelectInstance) {
        const code = it.cargo_code;
        if (code != null) {
          const value = String(code);
          this.cargoSelectInstance.addOption({
            value,
            text: `${value} — ${it.cargo_name || ""}`,
          });
          this.cargoSelectInstance.setValue(value, true);
        } else {
          this.cargoSelectInstance.clear(true);
        }
      }
      if (this.originStationSelectInstance) {
        const originCode = it.origin_esr_code;
        if (originCode != null) {
          const value = String(originCode);
          this.originStationSelectInstance.addOption({
            value,
            text: `${value} — ${it.origin_station_name || ""}`,
          });
          this.originStationSelectInstance.setValue(value, true);
        } else {
          this.originStationSelectInstance.clear(true);
        }
      }
      if (this.destinationStationSelectInstance) {
        const destCode = it.destination_esr_code;
        if (destCode != null) {
          const value = String(destCode);
          this.destinationStationSelectInstance.addOption({
            value,
            text: `${value} — ${it.destination_station_name || ""}`,
          });
          this.destinationStationSelectInstance.setValue(value, true);
        } else {
          this.destinationStationSelectInstance.clear(true);
        }
      }

      document.getElementById("routeShipperHolding").value =
        it.shipper_holding || "";
      document.getElementById("routeShipper").value = it.shipper || "";
      document.getElementById("routeWagonKindId").value =
        it.wagon_kind_id ?? "";
      document.getElementById("routeShipmentTypeId").value =
        it.shipment_type_id ?? "";
      document.getElementById("routeMessageTypeId").value =
        it.message_type_id ?? "";
      document.getElementById("routeCode").value = it.route_code || "";
      document.getElementById("routeDistanceLoaded").value =
        it.distance_loaded_km ?? "";
      document.getElementById("routeDistanceEmpty").value =
        it.distance_empty_km ?? "";
      document.getElementById("routeLoadTonsPerWagon").value =
        it.load_tons_per_wagon ?? "";
      document.getElementById("routeEmptyReturnPct").value =
        it.empty_wagon_return_pct ?? "";
      document.getElementById("routeDeliveryLoaded").value =
        it.delivery_time_loaded_days ?? "";
      document.getElementById("routeDeliveryEmpty").value =
        it.delivery_time_empty_days ?? "";
      document.getElementById("routeDeliveryOps").value =
        it.delivery_time_ops_days ?? "";
      document.getElementById("routeRatePerWagon").value =
        it.rate_per_wagon_per_day ?? "";
      document.getElementById("routeRzdLoaded").value =
        it.rzd_cost_loaded_per_ton ?? "";
      document.getElementById("routeRzdEmpty").value =
        it.rzd_cost_empty_per_ton ?? "";
      document.getElementById("routeRzdTotal").value =
        it.rzd_cost_total_per_ton ?? "";
      document.getElementById("routeOperatorsCost").value =
        it.operators_cost_per_ton ?? "";
      document.getElementById("routeTransshipmentCost").value =
        it.transshipment_cost_per_ton ?? "";
      document.getElementById("routeExcise").value =
        it.excise_or_duty_per_ton ?? "";
      document.getElementById("routeTransportTotal").value =
        it.transport_total_cost_per_ton ?? "";
      document.getElementById("routeProductionCost").value =
        it.production_cost_per_ton ?? "";
      document.getElementById("routeTotalCost").value =
        it.total_cost_per_ton ?? "";
      document.getElementById("routeMarketPrice").value =
        it.market_price_per_ton ?? "";

      // Заполняем summary из данных маршрута
      this.summaryState.origin = it.origin_esr_code
        ? {
            esr_code: it.origin_esr_code,
            full_name: it.origin_station_name || "",
            region_full_name: it.origin_region_full_name || "",
            railroad_code: it.origin_railroad_code || "",
            railroad_name: it.origin_railroad_name || "",
            railroad_direction: it.origin_railroad_direction || "",
          }
        : null;
      this.summaryState.destination = it.destination_esr_code
        ? {
            esr_code: it.destination_esr_code,
            full_name: it.destination_station_name || "",
            region_full_name: it.destination_region_full_name || "",
            railroad_code: it.destination_railroad_code || "",
            railroad_name: it.destination_railroad_name || "",
            railroad_direction: it.destination_railroad_direction || "",
          }
        : null;
      this.summaryState.messageType = it.message_type_id
        ? {
            id: String(it.message_type_id),
            name: it.message_type_name || "",
            direction: null,
          }
        : null;
      this.updateSummaryView();

      modal.show();
      openFirstAccordionSection();
    }

    collectRoutePayload() {
      const payload = {};
      payload.route_set_id = this.state.routeSetId;
      if (this.cargoSelectInstance) {
        const value = this.cargoSelectInstance.getValue();
        payload.cargo_code = value ? String(value).trim() : "";
      } else if (this.hasCargoSelectTarget) {
        payload.cargo_code = this.cargoSelectTarget.value.trim();
      } else {
        payload.cargo_code = "";
      }
      payload.shipper_holding =
        document.getElementById("routeShipperHolding").value.trim();
      payload.shipper = document.getElementById("routeShipper").value.trim();

      if (this.originStationSelectInstance) {
        const origin = this.originStationSelectInstance.getValue();
        payload.origin_esr_code = origin ? String(origin).trim() : "";
      } else if (this.hasOriginStationSelectTarget) {
        payload.origin_esr_code =
          this.originStationSelectTarget.value.trim();
      } else {
        payload.origin_esr_code = "";
      }

      if (this.destinationStationSelectInstance) {
        const dest = this.destinationStationSelectInstance.getValue();
        payload.destination_esr_code = dest ? String(dest).trim() : "";
      } else if (this.hasDestinationStationSelectTarget) {
        payload.destination_esr_code =
          this.destinationStationSelectTarget.value.trim();
      } else {
        payload.destination_esr_code = "";
      }
      payload.wagon_kind_id =
        document.getElementById("routeWagonKindId").value.trim();
      payload.shipment_type_id =
        document.getElementById("routeShipmentTypeId").value.trim();
      payload.message_type_id =
        document.getElementById("routeMessageTypeId").value.trim();
      payload.route_code = document.getElementById("routeCode").value.trim();

      payload.distance_loaded_km =
        document.getElementById("routeDistanceLoaded").value.trim();
      payload.distance_empty_km =
        document.getElementById("routeDistanceEmpty").value.trim();
      payload.load_tons_per_wagon =
        document.getElementById("routeLoadTonsPerWagon").value.trim();
      payload.empty_wagon_return_pct =
        document.getElementById("routeEmptyReturnPct").value.trim();
      payload.delivery_time_loaded_days =
        document.getElementById("routeDeliveryLoaded").value.trim();
      payload.delivery_time_empty_days =
        document.getElementById("routeDeliveryEmpty").value.trim();
      payload.delivery_time_ops_days =
        document.getElementById("routeDeliveryOps").value.trim();
      payload.rate_per_wagon_per_day =
        document.getElementById("routeRatePerWagon").value.trim();
      payload.rzd_cost_loaded_per_ton =
        document.getElementById("routeRzdLoaded").value.trim();
      payload.rzd_cost_empty_per_ton =
        document.getElementById("routeRzdEmpty").value.trim();
      payload.rzd_cost_total_per_ton =
        document.getElementById("routeRzdTotal").value.trim();
      payload.operators_cost_per_ton =
        document.getElementById("routeOperatorsCost").value.trim();
      payload.transshipment_cost_per_ton =
        document.getElementById("routeTransshipmentCost").value.trim();
      payload.excise_or_duty_per_ton =
        document.getElementById("routeExcise").value.trim();
      payload.transport_total_cost_per_ton =
        document.getElementById("routeTransportTotal").value.trim();
      payload.production_cost_per_ton =
        document.getElementById("routeProductionCost").value.trim();
      payload.total_cost_per_ton =
        document.getElementById("routeTotalCost").value.trim();
      payload.market_price_per_ton =
        document.getElementById("routeMarketPrice").value.trim();

      return payload;
    }
  }

  application.register("routes", RoutesController);
})();

