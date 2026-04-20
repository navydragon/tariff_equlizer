import { fetchJson } from "../lib/http.js";
import { escapeHtml, setVisible } from "../lib/dom.js";
import { renderErrors } from "../lib/errors.js";
import { renderPagination } from "../lib/pagination.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for simple-dict.");
    return;
  }

  class SimpleDictController extends Stimulus.Controller {
    static targets = [
      "searchInput",
      "activeFilter",
      "pageSize",
      "tableBody",
      "summary",
      "pagination",
      "loading",
      "empty",
      "createModal",
      "editModal",
      "createErrors",
      "editErrors",
      "createName",
      "createCode",
      "createPosition",
      "createIsActive",
      "editId",
      "editName",
      "editCode",
      "editPosition",
      "editIsActive",
    ];

    static values = {
      listUrl: String,
      detailUrlTemplate: String,
      createUrl: String,
      updateUrlTemplate: String,
      deleteUrlTemplate: String,
      pageSizeDefault: { type: Number, default: 20 },
      debounceMs: { type: Number, default: 400 },
    };

    connect() {
      this.state = {
        page: 1,
        pageSize: this.pageSizeDefaultValue || 20,
        totalPages: 1,
        searchTimeout: null,
      };
      this.loadItems(1);
    }

    // === Actions ===
    search() {
      this.state.page = 1;
      this.loadItems(1);
    }

    reset() {
      if (this.hasSearchInputTarget) {
        this.searchInputTarget.value = "";
      }
      if (this.hasActiveFilterTarget) {
        this.activeFilterTarget.value = "";
      }
      if (this.hasPageSizeTarget) {
        this.pageSizeTarget.value = String(this.pageSizeDefaultValue || 20);
      }
      this.state.page = 1;
      this.loadItems(1);
    }

    onSearchInput() {
      clearTimeout(this.state.searchTimeout);
      const delay = this.debounceMsValue || 400;
      this.state.searchTimeout = setTimeout(() => {
        this.state.page = 1;
        this.loadItems(1);
      }, delay);
    }

    onFilterChange() {
      this.state.page = 1;
      this.loadItems(1);
    }

    async createItem() {
      const name = this.hasCreateNameTarget
        ? this.createNameTarget.value.trim()
        : "";
      if (!name) {
        renderErrors(this.createErrorsTarget, ["Название обязательно"]);
        return;
      }

      const payload = {
        name,
        code: this.hasCreateCodeTarget
          ? this.createCodeTarget.value.trim()
          : "",
        position: this.hasCreatePositionTarget
          ? this.createPositionTarget.value
          : 0,
        is_active: this.hasCreateIsActiveTarget
          ? this.createIsActiveTarget.checked
          : true,
      };

      const url = this.createUrlValue;
      if (!url) {
        console.error("createUrlValue is not defined for simple-dict");
        return;
      }

      const { data } = await fetchJson(url, {
        method: "POST",
        body: payload,
      });

      if (!data || !data.success) {
        renderErrors(
          this.createErrorsTarget,
          (data && data.errors) || ["Ошибка создания"],
        );
        return;
      }

      renderErrors(this.createErrorsTarget, []);
      if (this.hasCreateModalTarget) {
        const modal = bootstrap.Modal.getInstance(this.createModalTarget);
        if (modal) modal.hide();
      }
      if (this.hasCreateNameTarget) this.createNameTarget.value = "";
      if (this.hasCreateCodeTarget) this.createCodeTarget.value = "";
      if (this.hasCreatePositionTarget)
        this.createPositionTarget.value = "0";
      if (this.hasCreateIsActiveTarget)
        this.createIsActiveTarget.checked = true;
      this.loadItems(1);
    }

    async updateItem() {
      const id = this.hasEditIdTarget ? this.editIdTarget.value : "";
      if (!id) return;

      const name = this.hasEditNameTarget
        ? this.editNameTarget.value.trim()
        : "";
      if (!name) {
        renderErrors(this.editErrorsTarget, ["Название обязательно"]);
        return;
      }

      const payload = {
        name,
        code: this.hasEditCodeTarget ? this.editCodeTarget.value.trim() : "",
        position: this.hasEditPositionTarget
          ? this.editPositionTarget.value
          : 0,
        is_active: this.hasEditIsActiveTarget
          ? this.editIsActiveTarget.checked
          : true,
      };

      const template = this.updateUrlTemplateValue;
      if (!template) {
        console.error("updateUrlTemplateValue is not defined for simple-dict");
        return;
      }
      const url = template.replace("0", encodeURIComponent(id));

      const { data } = await fetchJson(url, {
        method: "POST",
        body: payload,
      });

      if (!data || !data.success) {
        renderErrors(
          this.editErrorsTarget,
          (data && data.errors) || ["Ошибка сохранения"],
        );
        return;
      }

      renderErrors(this.editErrorsTarget, []);
      if (this.hasEditModalTarget) {
        const modal = bootstrap.Modal.getInstance(this.editModalTarget);
        if (modal) modal.hide();
      }
      this.loadItems(this.state.page);
    }

    async openEdit(event) {
      const id = event.currentTarget.dataset.id;
      if (!id) return;

      const template = this.detailUrlTemplateValue;
      if (!template) {
        console.error("detailUrlTemplateValue is not defined for simple-dict");
        return;
      }
      const url = template.replace("0", encodeURIComponent(id));

      const { data } = await fetchJson(url, { method: "GET" });
      if (!data || !data.success || !data.item) {
        renderErrors(this.editErrorsTarget, [
          "Не удалось загрузить запись",
        ]);
        return;
      }

      const it = data.item;
      if (this.hasEditIdTarget) this.editIdTarget.value = it.id;
      if (this.hasEditNameTarget) this.editNameTarget.value = it.name || "";
      if (this.hasEditCodeTarget) this.editCodeTarget.value = it.code || "";
      if (this.hasEditPositionTarget)
        this.editPositionTarget.value = it.position ?? 0;
      if (this.hasEditIsActiveTarget)
        this.editIsActiveTarget.checked = !!it.is_active;

      renderErrors(this.editErrorsTarget, []);
      if (this.hasEditModalTarget) {
        const modal = bootstrap.Modal.getOrCreateInstance(this.editModalTarget);
        modal.show();
      }
    }

    async delete(event) {
      const id = event.currentTarget.dataset.id;
      if (!id) return;
      if (
        !window.confirm(
          "Вы действительно хотите удалить эту запись?",
        )
      ) {
        return;
      }

      const template = this.deleteUrlTemplateValue;
      if (!template) {
        console.error("deleteUrlTemplateValue is not defined for simple-dict");
        return;
      }
      const url = template.replace("0", encodeURIComponent(id));

      const { data } = await fetchJson(url, { method: "POST", body: null });
      if (!data || !data.success) {
        window.alert(
          ((data && data.errors) || ["Ошибка удаления"]).join("\n"),
        );
        return;
      }

      this.loadItems(this.state.page);
    }

    // === Внутренняя логика ===
    buildParams() {
      const params = new URLSearchParams();
      params.set("page", String(this.state.page));

      const pageSize =
        (this.hasPageSizeTarget && parseInt(this.pageSizeTarget.value, 10)) ||
        this.pageSizeDefaultValue ||
        20;
      this.state.pageSize = pageSize;
      params.set("page_size", String(pageSize));

      if (this.hasSearchInputTarget) {
        const search = this.searchInputTarget.value.trim();
        if (search) params.set("search", search);
      }

      if (this.hasActiveFilterTarget) {
        const active = this.activeFilterTarget.value;
        if (active !== "") params.set("is_active", active);
      }

      return params;
    }

    async loadItems(page) {
      if (page) this.state.page = page;

      const params = this.buildParams();
      if (this.hasLoadingTarget) setVisible(this.loadingTarget, true);
      if (this.hasEmptyTarget) setVisible(this.emptyTarget, false);
      if (this.hasTableBodyTarget) this.tableBodyTarget.innerHTML = "";

      const url = this.listUrlValue;
      if (!url) {
        console.error("listUrlValue is not defined for simple-dict");
        return;
      }

      const { data } = await fetchJson(url + "?" + params.toString(), {
        method: "GET",
      });

      if (this.hasLoadingTarget) setVisible(this.loadingTarget, false);

      const tbody = this.hasTableBodyTarget ? this.tableBodyTarget : null;
      const empty = this.hasEmptyTarget ? this.emptyTarget : null;

      if (!tbody || !empty) return;

      if (!data || !data.success) {
        tbody.innerHTML =
          '<tr><td colspan="5"><div class="alert alert-danger mb-0">' +
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
        tbody.innerHTML = items.map((it) => this.renderRow(it)).join("");
      }

      this.state.page = data.page || 1;
      this.state.totalPages = data.total_pages || 1;
      this.updateSummary(data.total || 0);
      this.updatePagination();
    }

    renderRow(item) {
      const code = item.code
        ? escapeHtml(String(item.code))
        : '<span class="text-muted">—</span>';
      const active = item.is_active
        ? '<span class="badge bg-green-lt">Да</span>'
        : '<span class="badge bg-secondary-lt">Нет</span>';

      return `
        <tr data-id="${item.id}">
          <td>${escapeHtml(item.name || "")}</td>
          <td>${code}</td>
          <td>${escapeHtml(String(item.position ?? 0))}</td>
          <td>${active}</td>
          <td class="text-end">
            <div class="btn-group" role="group" aria-label="Действия">
              <button
                type="button"
                class="btn btn-sm btn-outline-primary"
                data-id="${item.id}"
                data-action="click->simple-dict#openEdit"
                title="Редактировать"
              >
                <i class="ti ti-edit"></i>
              </button>
              <button
                type="button"
                class="btn btn-sm btn-outline-danger"
                data-id="${item.id}"
                data-action="click->simple-dict#delete"
                title="Удалить"
              >
                <i class="ti ti-trash"></i>
              </button>
            </div>
          </td>
        </tr>
      `;
    }

    updateSummary(total) {
      if (!this.hasSummaryTarget) return;
      const from = (this.state.page - 1) * this.state.pageSize + 1;
      const to = Math.min(this.state.page * this.state.pageSize, total || 0);
      this.summaryTarget.textContent = total
        ? `Показаны ${from}–${to} из ${total} записей`
        : "Нет записей";
    }

    updatePagination() {
      if (!this.hasPaginationTarget) return;
      renderPagination(this.paginationTarget, {
        page: this.state.page,
        totalPages: this.state.totalPages,
        onPage: (p) => this.loadItems(p),
      });
    }
  }

  application.register("simple-dict", SimpleDictController);
})();

