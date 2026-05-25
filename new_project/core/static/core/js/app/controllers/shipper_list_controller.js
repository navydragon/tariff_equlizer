(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for shipper-list.");
    return;
  }

  application.register(
    "shipper-list",
    class extends Stimulus.Controller {
      static targets = [
        "loading",
        "empty",
        "tableBody",
        "summary",
        "pagination",
        "searchInput",
        "holdingFilter",
        "pageSize",
        "searchButton",
        "resetButton",
        "createErrors",
        "editErrors",
      ];

      static values = {
        listUrl: String,
        detailUrlTemplate: String,
        createUrl: String,
        updateUrlTemplate: String,
        deleteUrlTemplate: String,
      };

      connect() {
        this.state = { page: 1, pageSize: 20, totalPages: 1 };
        this.attachFilters();
        this.attachModals();
        this.loadItems(1);
      }

      getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== "") {
          const cookies = document.cookie.split(";");
          for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + "=") {
              cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
              break;
            }
          }
        }
        return cookieValue;
      }

      escapeHtml(text) {
        if (text == null) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
      }

      buildUrl(template, id) {
        return String(template || "").replace("/0/", "/" + String(id) + "/");
      }

      showErrors(target, errors) {
        if (!target) return;
        if (!errors || !errors.length) {
          target.innerHTML = "";
          return;
        }
        target.innerHTML =
          '<div class="alert alert-danger mb-0">' +
          errors.map((e) => this.escapeHtml(e)).join("<br>") +
          "</div>";
      }

      attachFilters() {
        if (this.hasSearchButtonTarget) {
          this.searchButtonTarget.addEventListener("click", () => this.loadItems(1));
        }
        if (this.hasResetButtonTarget) {
          this.resetButtonTarget.addEventListener("click", () => {
            if (this.hasSearchInputTarget) this.searchInputTarget.value = "";
            if (this.hasHoldingFilterTarget) this.holdingFilterTarget.value = "";
            if (this.hasPageSizeTarget) this.pageSizeTarget.value = "20";
            this.loadItems(1);
          });
        }
        if (this.hasSearchInputTarget) {
          this.searchInputTarget.addEventListener("keydown", (e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              this.loadItems(1);
            }
          });
        }
      }

      attachModals() {
        const createSubmit = document.getElementById("shipperCreateSubmit");
        if (createSubmit) {
          createSubmit.addEventListener("click", () => this.createItem());
        }
        const editSubmit = document.getElementById("shipperEditSubmit");
        if (editSubmit) {
          editSubmit.addEventListener("click", () => this.updateItem());
        }
      }

      showLoading(isLoading) {
        if (!this.hasLoadingTarget || !this.hasEmptyTarget || !this.hasTableBodyTarget) {
          return;
        }
        if (isLoading) {
          this.loadingTarget.style.display = "block";
          this.emptyTarget.style.display = "none";
          this.tableBodyTarget.innerHTML = "";
        } else {
          this.loadingTarget.style.display = "none";
        }
      }

      loadItems(page) {
        if (page) this.state.page = page;

        this.state.pageSize = parseInt(
          (this.hasPageSizeTarget && this.pageSizeTarget.value) || "20",
          10,
        );

        const params = new URLSearchParams();
        params.set("page", String(this.state.page));
        params.set("page_size", String(this.state.pageSize));

        const search =
          (this.hasSearchInputTarget && this.searchInputTarget.value.trim()) || "";
        if (search) params.set("search", search);

        const holding =
          (this.hasHoldingFilterTarget && this.holdingFilterTarget.value.trim()) ||
          "";
        if (holding) params.set("holding", holding);

        this.showLoading(true);

        fetch(`${this.listUrlValue}?${params.toString()}`, {
          method: "GET",
          headers: { "X-CSRFToken": this.getCookie("csrftoken") },
        })
          .then((r) => r.json())
          .then((data) => {
            this.showLoading(false);
            if (!data.success) {
              this.tableBodyTarget.innerHTML =
                '<tr><td colspan="5"><div class="alert alert-danger mb-0">' +
                this.escapeHtml((data.errors || []).join(", ") || "Ошибка загрузки") +
                "</div></td></tr>";
              return;
            }

            if (!data.items || data.items.length === 0) {
              this.tableBodyTarget.innerHTML = "";
              this.emptyTarget.style.display = "block";
            } else {
              this.emptyTarget.style.display = "none";
              this.tableBodyTarget.innerHTML = data.items
                .map((it) => this.rowHtml(it))
                .join("");
            }

            this.state.page = data.page || 1;
            this.state.totalPages = data.total_pages || 1;
            this.updateSummary(data.total || 0);
            this.updatePagination();
            this.attachRowHandlers();
          })
          .catch((err) => {
            console.error(err);
            this.showLoading(false);
            this.tableBodyTarget.innerHTML =
              '<tr><td colspan="5"><div class="alert alert-danger mb-0">Ошибка загрузки</div></td></tr>';
          });
      }

      rowHtml(item) {
        const okpo =
          item.okpo != null && item.okpo !== ""
            ? this.escapeHtml(String(item.okpo))
            : '<span class="text-muted">—</span>';
        const inn = item.inn
          ? this.escapeHtml(item.inn)
          : '<span class="text-muted">—</span>';
        const holding = item.holding
          ? this.escapeHtml(item.holding)
          : '<span class="text-muted">—</span>';

        return `
          <tr data-id="${item.id}">
            <td>${this.escapeHtml(item.name)}</td>
            <td>${okpo}</td>
            <td>${inn}</td>
            <td>${holding}</td>
            <td class="text-end">
              <div class="btn-group" role="group">
                <button type="button" class="btn btn-sm btn-outline-primary shipper-edit-btn" data-id="${item.id}" title="Редактировать">
                  <i class="ti ti-edit"></i>
                </button>
                <button type="button" class="btn btn-sm btn-outline-danger shipper-delete-btn" data-id="${item.id}" title="Удалить">
                  <i class="ti ti-trash"></i>
                </button>
              </div>
            </td>
          </tr>`;
      }

      updateSummary(total) {
        if (!this.hasSummaryTarget) return;
        const from = (this.state.page - 1) * this.state.pageSize + 1;
        const to = Math.min(this.state.page * this.state.pageSize, total);
        this.summaryTarget.textContent = total
          ? `Показаны ${from}–${to} из ${total} записей`
          : "Нет записей";
      }

      updatePagination() {
        if (!this.hasPaginationTarget) return;
        const container = this.paginationTarget;
        const page = this.state.page;
        const totalPages = this.state.totalPages || 1;
        container.innerHTML = "";

        const add = (label, target, disabled, active) => {
          const li = document.createElement("li");
          li.className = "page-item";
          if (disabled) li.classList.add("disabled");
          if (active) li.classList.add("active");
          const a = document.createElement("a");
          a.className = "page-link";
          a.href = "#";
          a.textContent = label;
          if (!disabled) {
            a.addEventListener("click", (e) => {
              e.preventDefault();
              if (target !== page) this.loadItems(target);
            });
          }
          li.appendChild(a);
          container.appendChild(li);
        };

        add("‹", page - 1, page <= 1, false);
        let start = Math.max(1, page - 2);
        let end = Math.min(totalPages, start + 4);
        start = Math.max(1, end - 4);
        for (let p = start; p <= end; p++) add(String(p), p, false, p === page);
        add("›", page + 1, page >= totalPages, false);
      }

      attachRowHandlers() {
        this.tableBodyTarget.querySelectorAll(".shipper-edit-btn").forEach((btn) => {
          btn.addEventListener("click", () => this.openEdit(btn.dataset.id));
        });
        this.tableBodyTarget.querySelectorAll(".shipper-delete-btn").forEach((btn) => {
          btn.addEventListener("click", () => this.deleteItem(btn.dataset.id));
        });
      }

      openEdit(id) {
        fetch(this.buildUrl(this.detailUrlTemplateValue, id), {
          headers: { "X-CSRFToken": this.getCookie("csrftoken") },
        })
          .then((r) => r.json())
          .then((data) => {
            if (!data.success || !data.item) {
              alert((data.errors || []).join(", ") || "Ошибка загрузки");
              return;
            }
            const it = data.item;
            document.getElementById("shipperEditId").value = it.id;
            document.getElementById("shipperEditName").value = it.name || "";
            document.getElementById("shipperEditOkpo").value =
              it.okpo != null ? it.okpo : "";
            document.getElementById("shipperEditInn").value = it.inn || "";
            document.getElementById("shipperEditHolding").value = it.holding || "";
            this.showErrors(this.hasEditErrorsTarget ? this.editErrorsTarget : null, []);
            bootstrap.Modal.getOrCreateInstance(
              document.getElementById("shipperEditModal"),
            ).show();
          });
      }

      createItem() {
        const payload = {
          name: document.getElementById("shipperCreateName").value.trim(),
          okpo: document.getElementById("shipperCreateOkpo").value.trim(),
          inn: document.getElementById("shipperCreateInn").value.trim(),
          holding: document.getElementById("shipperCreateHolding").value.trim(),
        };

        fetch(this.createUrlValue, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": this.getCookie("csrftoken"),
          },
          body: JSON.stringify(payload),
        })
          .then((r) => r.json())
          .then((data) => {
            if (!data.success) {
              this.showErrors(
                this.hasCreateErrorsTarget ? this.createErrorsTarget : null,
                data.errors,
              );
              return;
            }
            bootstrap.Modal.getInstance(
              document.getElementById("shipperCreateModal"),
            )?.hide();
            document.getElementById("shipperCreateForm").reset();
            this.loadItems(1);
          });
      }

      updateItem() {
        const id = document.getElementById("shipperEditId").value;
        const payload = {
          name: document.getElementById("shipperEditName").value.trim(),
          okpo: document.getElementById("shipperEditOkpo").value.trim(),
          inn: document.getElementById("shipperEditInn").value.trim(),
          holding: document.getElementById("shipperEditHolding").value.trim(),
        };

        fetch(this.buildUrl(this.updateUrlTemplateValue, id), {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": this.getCookie("csrftoken"),
          },
          body: JSON.stringify(payload),
        })
          .then((r) => r.json())
          .then((data) => {
            if (!data.success) {
              this.showErrors(
                this.hasEditErrorsTarget ? this.editErrorsTarget : null,
                data.errors,
              );
              return;
            }
            bootstrap.Modal.getInstance(
              document.getElementById("shipperEditModal"),
            )?.hide();
            this.loadItems(this.state.page);
          });
      }

      deleteItem(id) {
        if (!window.confirm("Удалить грузоотправителя?")) return;

        fetch(this.buildUrl(this.deleteUrlTemplateValue, id), {
          method: "POST",
          headers: { "X-CSRFToken": this.getCookie("csrftoken") },
        })
          .then((r) => r.json())
          .then((data) => {
            if (!data.success) {
              alert((data.errors || []).join(", ") || "Ошибка удаления");
              return;
            }
            this.loadItems(this.state.page);
          });
      }
    },
  );
})();
