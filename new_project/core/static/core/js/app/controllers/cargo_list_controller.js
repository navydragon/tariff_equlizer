(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for cargo-list.");
    return;
  }

  application.register(
    "cargo-list",
    class extends Stimulus.Controller {
      static targets = [
        "loading",
        "empty",
        "tableBody",
        "summary",
        "pagination",
        "searchInput",
        "groupFilter",
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
        debounceMs: Number,
      };

      connect() {
        this.state = {
          page: 1,
          pageSize: 20,
          totalPages: 1,
          searchTimeout: null,
        };
        this.attachFilters();
        this.attachCreateModal();
        this.attachEditModal();
        this.loadCargos(1);
      }

      // === Утилиты ===
      getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== "") {
          const cookies = document.cookie.split(";");
          for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === name + "=") {
              cookieValue = decodeURIComponent(
                cookie.substring(name.length + 1),
              );
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

      // === Загрузка списка ===
      showLoading(isLoading) {
        const loading = this.hasLoadingTarget ? this.loadingTarget : null;
        const empty = this.hasEmptyTarget ? this.emptyTarget : null;
        const tbody = this.hasTableBodyTarget ? this.tableBodyTarget : null;

        if (!loading || !empty || !tbody) return;

        if (isLoading) {
          loading.style.display = "block";
          empty.style.display = "none";
          tbody.innerHTML = "";
        } else {
          loading.style.display = "none";
        }
      }

      loadCargos(page) {
        if (page) {
          this.state.page = page;
        }

        const searchInput = this.hasSearchInputTarget
          ? this.searchInputTarget
          : null;
        const groupSelect = this.hasGroupFilterTarget
          ? this.groupFilterTarget
          : null;
        const pageSizeSelect = this.hasPageSizeTarget
          ? this.pageSizeTarget
          : null;

        this.state.pageSize = parseInt(
          (pageSizeSelect && pageSizeSelect.value) || "20",
          10,
        );

        const params = new URLSearchParams();
        params.set("page", this.state.page.toString());
        params.set("page_size", this.state.pageSize.toString());

        const search =
          (searchInput && searchInput.value && searchInput.value.trim()) || "";
        if (search) {
          params.set("search", search);
        }

        const groupValue =
          (groupSelect && groupSelect.value && groupSelect.value.trim()) || "";
        if (groupValue) {
          params.set("cargo_group_code", groupValue);
        }

        this.showLoading(true);

        const listUrl = this.listUrlValue || "";

        fetch(listUrl + "?" + params.toString(), {
          method: "GET",
          headers: {
            "X-CSRFToken": this.getCookie("csrftoken"),
          },
        })
          .then((response) => response.json())
          .then((data) => {
            this.showLoading(false);
            const tbody = this.hasTableBodyTarget ? this.tableBodyTarget : null;
            const empty = this.hasEmptyTarget ? this.emptyTarget : null;

            if (!tbody || !empty) return;

            if (!data.success) {
              tbody.innerHTML =
                '<tr><td colspan="4"><div class="alert alert-danger mb-0">' +
                this.escapeHtml(
                  (data.errors || []).join(", ") || "Ошибка загрузки",
                ) +
                "</div></td></tr>";
              return;
            }

            if (!data.items || data.items.length === 0) {
              tbody.innerHTML = "";
              empty.style.display = "block";
            } else {
              empty.style.display = "none";
              tbody.innerHTML = data.items
                .map((it) => this.createRowHtml(it))
                .join("");
            }

            this.state.page = data.page || 1;
            this.state.pageSize = data.page_size || this.state.pageSize;
            this.state.totalPages = data.total_pages || 1;

            this.updateSummary(data.total);
            this.updatePagination();
            this.attachRowHandlers();
          })
          .catch((error) => {
            console.error("Ошибка загрузки грузов:", error);
            const tbody = this.hasTableBodyTarget ? this.tableBodyTarget : null;
            if (!tbody) return;
            tbody.innerHTML =
              '<tr><td colspan="4"><div class="alert alert-danger mb-0">Ошибка загрузки грузов</div></td></tr>';
          });
      }

      createRowHtml(item) {
        const groupName = item.cargo_group_name
          ? this.escapeHtml(item.cargo_group_name)
          : '<span class="text-muted">—</span>';

        return `
      <tr data-code="${item.code}">
        <td>${item.code}</td>
        <td>${this.escapeHtml(item.name)}</td>
        <td>${groupName}</td>
        <td class="text-end">
          <div class="btn-group" role="group" aria-label="Действия">
            <button
              type="button"
              class="btn btn-sm btn-outline-primary cargo-edit-btn"
              data-code="${item.code}"
              title="Редактировать"
            >
              <i class="ti ti-edit"></i>
            </button>
            <button
              type="button"
              class="btn btn-sm btn-outline-danger cargo-delete-btn"
              data-code="${item.code}"
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
        const summary = this.hasSummaryTarget ? this.summaryTarget : null;
        if (!summary) return;

        const from = (this.state.page - 1) * this.state.pageSize + 1;
        const to = Math.min(this.state.page * this.state.pageSize, total || 0);
        if (!total) {
          summary.textContent = "Нет записей";
        } else {
          summary.textContent =
            "Показаны " + from + "–" + to + " из " + total + " записей";
        }
      }

      updatePagination() {
        const container = this.hasPaginationTarget ? this.paginationTarget : null;
        if (!container) return;

        const page = this.state.page;
        const totalPages = this.state.totalPages || 1;
        container.innerHTML = "";

        const createPageItem = (label, targetPage, disabled, active) => {
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
              if (targetPage && targetPage !== this.state.page) {
                this.loadCargos(targetPage);
              }
            });
          }

          li.appendChild(a);
          container.appendChild(li);
        };

        createPageItem("‹", page - 1, page <= 1, false);

        const maxButtons = 5;
        let start = Math.max(1, page - Math.floor(maxButtons / 2));
        let end = start + maxButtons - 1;
        if (end > totalPages) {
          end = totalPages;
          start = Math.max(1, end - maxButtons + 1);
        }

        for (let p = start; p <= end; p++) {
          createPageItem(p.toString(), p, false, p === page);
        }

        createPageItem("›", page + 1, page >= totalPages, false);
      }

      // === Обработчики строк ===
      attachRowHandlers() {
        const tbody = this.hasTableBodyTarget ? this.tableBodyTarget : null;
        if (!tbody) return;

        tbody.querySelectorAll(".cargo-edit-btn").forEach((btn) => {
          btn.addEventListener("click", () => {
            const code = btn.dataset.code;
            this.openEditModal(code);
          });
        });

        tbody.querySelectorAll(".cargo-delete-btn").forEach((btn) => {
          btn.addEventListener("click", () => {
            const code = btn.dataset.code;
            this.deleteCargo(code);
          });
        });
      }

      openEditModal(code) {
        const template = this.detailUrlTemplateValue || "";
        const url = template.replace("/0/", "/" + code + "/");

        fetch(url, {
          method: "GET",
          headers: {
            "X-CSRFToken": this.getCookie("csrftoken"),
          },
        })
          .then((response) => response.json())
          .then((data) => {
            if (!data.success || !data.item) {
              alert(
                "Ошибка загрузки груза: " +
                  this.escapeHtml(
                    (data.errors || []).join(", ") || "Неизвестная ошибка",
                  ),
              );
              return;
            }

            const item = data.item;
            document.getElementById("cargoEditCode").value = item.code;
            document.getElementById("cargoEditCodeDisplay").value = item.code;
            document.getElementById("cargoEditName").value = item.name || "";
            const groupSelect = document.getElementById("cargoEditGroup");
            groupSelect.value = item.cargo_group_code || "";

            const modalEl = document.getElementById("cargoEditModal");
            const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
          })
          .catch((error) => {
            console.error("Ошибка загрузки груза:", error);
            alert("Ошибка загрузки груза");
          });
      }

      deleteCargo(code) {
        if (!confirm("Вы уверены, что хотите удалить груз " + code + "?")) {
          return;
        }

        const template = this.deleteUrlTemplateValue || "";
        const url = template.replace("/0/", "/" + code + "/");

        fetch(url, {
          method: "POST",
          headers: {
            "X-CSRFToken": this.getCookie("csrftoken"),
          },
        })
          .then((response) => response.json())
          .then((data) => {
            if (!data.success) {
              alert(
                "Ошибка удаления: " +
                  this.escapeHtml(
                    (data.errors || []).join(", ") || "Неизвестная ошибка",
                  ),
              );
            } else {
              this.loadCargos(this.state.page);
            }
          })
          .catch((error) => {
            console.error("Ошибка удаления груза:", error);
            alert("Ошибка удаления груза");
          });
      }

      // === Фильтры ===
      attachFilters() {
        const searchInput = this.hasSearchInputTarget
          ? this.searchInputTarget
          : null;
        const searchButton = this.hasSearchButtonTarget
          ? this.searchButtonTarget
          : null;
        const resetButton = this.hasResetButtonTarget
          ? this.resetButtonTarget
          : null;
        const groupSelect = this.hasGroupFilterTarget
          ? this.groupFilterTarget
          : null;
        const pageSizeSelect = this.hasPageSizeTarget
          ? this.pageSizeTarget
          : null;

        if (searchButton) {
          searchButton.addEventListener("click", () => {
            this.state.page = 1;
            this.loadCargos(1);
          });
        }

        if (resetButton && searchInput && groupSelect && pageSizeSelect) {
          resetButton.addEventListener("click", () => {
            searchInput.value = "";
            groupSelect.value = "";
            pageSizeSelect.value = "20";
            this.state.page = 1;
            this.loadCargos(1);
          });
        }

        const debounceMs = this.hasDebounceMsValue
          ? this.debounceMsValue
          : 400;

        if (searchInput) {
          searchInput.addEventListener("input", () => {
            clearTimeout(this.state.searchTimeout);
            this.state.searchTimeout = setTimeout(() => {
              this.state.page = 1;
              this.loadCargos(1);
            }, debounceMs);
          });
        }

        if (groupSelect) {
          groupSelect.addEventListener("change", () => {
            this.state.page = 1;
            this.loadCargos(1);
          });
        }

        if (pageSizeSelect) {
          pageSizeSelect.addEventListener("change", () => {
            this.state.page = 1;
            this.loadCargos(1);
          });
        }
      }

      // === Модалка создания ===
      attachCreateModal() {
        const submitBtn = document.getElementById("cargoCreateSubmit");
        const form = document.getElementById("cargoCreateForm");
        const errorsContainer = this.hasCreateErrorsTarget
          ? this.createErrorsTarget
          : document.getElementById("cargoCreateErrors");

        if (!submitBtn || !form || !errorsContainer) return;

        submitBtn.addEventListener("click", () => {
          errorsContainer.innerHTML = "";
          const code = parseInt(
            document.getElementById("cargoCreateCode").value,
            10,
          );
          const name = document.getElementById("cargoCreateName").value;
          const groupValue = document.getElementById("cargoCreateGroup").value;

          if (!code || code <= 0 || !name.trim()) {
            errorsContainer.innerHTML =
              '<div class="alert alert-danger">Заполните код и наименование</div>';
            return;
          }

          const payload = {
            code: code,
            name: name,
            cargo_group_code: groupValue || null,
          };

          const url = this.createUrlValue || "";

          fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": this.getCookie("csrftoken"),
            },
            body: JSON.stringify(payload),
          })
            .then((response) => response.json())
            .then((data) => {
              if (!data.success) {
                let html =
                  '<div class="alert alert-danger"><ul class="mb-0">';
                (data.errors || []).forEach((err) => {
                  html += "<li>" + this.escapeHtml(err) + "</li>";
                });
                html += "</ul></div>";
                errorsContainer.innerHTML = html;
                return;
              }

              const modalEl = document.getElementById("cargoCreateModal");
              const modal = bootstrap.Modal.getInstance(modalEl);
              if (modal) {
                modal.hide();
              }
              form.reset();
              this.loadCargos(this.state.page);
            })
            .catch((error) => {
              console.error("Ошибка создания груза:", error);
              errorsContainer.innerHTML =
                '<div class="alert alert-danger">Ошибка создания груза</div>';
            });
        });
      }

      // === Модалка редактирования ===
      attachEditModal() {
        const submitBtn = document.getElementById("cargoEditSubmit");
        const errorsContainer = this.hasEditErrorsTarget
          ? this.editErrorsTarget
          : document.getElementById("cargoEditErrors");

        if (!submitBtn || !errorsContainer) return;

        submitBtn.addEventListener("click", () => {
          errorsContainer.innerHTML = "";
          const code = document.getElementById("cargoEditCode").value;
          const name = document.getElementById("cargoEditName").value;
          const groupValue = document.getElementById("cargoEditGroup").value;

          if (!name.trim()) {
            errorsContainer.innerHTML =
              '<div class="alert alert-danger">Наименование обязательно</div>';
            return;
          }

          const payload = {
            name: name,
            cargo_group_code: groupValue || null,
          };

          const template = this.updateUrlTemplateValue || "";
          const url = template.replace("/0/", "/" + code + "/");

          fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "X-CSRFToken": this.getCookie("csrftoken"),
            },
            body: JSON.stringify(payload),
          })
            .then((response) => response.json())
            .then((data) => {
              if (!data.success) {
                let html =
                  '<div class="alert alert-danger"><ul class="mb-0">';
                (data.errors || []).forEach((err) => {
                  html += "<li>" + this.escapeHtml(err) + "</li>";
                });
                html += "</ul></div>";
                errorsContainer.innerHTML = html;
                return;
              }

              const modalEl = document.getElementById("cargoEditModal");
              const modal = bootstrap.Modal.getInstance(modalEl);
              if (modal) {
                modal.hide();
              }
              this.loadCargos(this.state.page);
            })
            .catch((error) => {
              console.error("Ошибка обновления груза:", error);
              errorsContainer.innerHTML =
                '<div class="alert alert-danger">Ошибка обновления груза</div>';
            });
        });
      }
    },
  );
})();

