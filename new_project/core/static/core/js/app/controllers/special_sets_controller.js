import { fetchJson } from "../lib/http.js";
import { escapeHtml, setVisible } from "../lib/dom.js";
import { renderErrors } from "../lib/errors.js";
import { showToast } from "../lib/toast.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for special-sets.");
    return;
  }

  class SpecialSetsController extends Stimulus.Controller {
    static targets = [
      "consumerTableBody",
      "foodTableBody",
      "consumerLoading",
      "foodLoading",
      "consumerEmpty",
      "foodEmpty",
      "consumerSummary",
      "foodSummary",
      "consumerCreateErrors",
      "foodCreateErrors",
      "consumerPositionInput",
      "foodPositionInput",
    ];

    static values = {
      consumerListUrl: String,
      foodListUrl: String,
      consumerCreateUrl: String,
      foodCreateUrl: String,
      consumerDeleteUrlTemplate: String,
      foodDeleteUrlTemplate: String,
    };

    connect() {
      this._bindModalCleanup("addConsumerPositionModal");
      this._bindModalCleanup("addFoodPositionModal");
      this.loadConsumerItems();
      this.loadFoodItems();
    }

    _bindModalCleanup(modalId) {
      const modalEl = document.getElementById(modalId);
      if (!modalEl) {
        return;
      }
      modalEl.addEventListener("hidden.bs.modal", () => {
        setTimeout(() => this._cleanupModalState(modalEl), 50);
      });
    }

    _cleanupModalState(modalEl) {
      document.querySelectorAll(".modal-backdrop").forEach((backdrop) => {
        backdrop.remove();
      });
      document.body.classList.remove("modal-open");
      document.body.style.overflow = "";
      document.body.style.paddingRight = "";
      if (!modalEl) {
        return;
      }
      modalEl.classList.remove("show");
      modalEl.style.display = "none";
      modalEl.setAttribute("aria-hidden", "true");
      modalEl.removeAttribute("aria-modal");
    }

    _closeModal(modalId) {
      const modalEl = document.getElementById(modalId);
      if (!modalEl || typeof bootstrap === "undefined") {
        return Promise.resolve();
      }

      if (!modalEl.classList.contains("show")) {
        this._cleanupModalState(modalEl);
        return Promise.resolve();
      }

      return new Promise((resolve) => {
        modalEl.addEventListener(
          "hidden.bs.modal",
          () => {
            setTimeout(() => {
              this._cleanupModalState(modalEl);
              resolve();
            }, 50);
          },
          { once: true },
        );

        const dismissBtn = modalEl.querySelector('[data-bs-dismiss="modal"]');
        if (dismissBtn) {
          dismissBtn.click();
          return;
        }

        const modal =
          bootstrap.Modal.getInstance(modalEl) ||
          bootstrap.Modal.getOrCreateInstance(modalEl);
        modal.hide();
      });
    }

    async loadConsumerItems() {
      await this.loadCategory("consumer", {
        listUrl: this.consumerListUrlValue,
        tableBody: this.consumerTableBodyTarget,
        loading: this.consumerLoadingTarget,
        empty: this.consumerEmptyTarget,
        summary: this.consumerSummaryTarget,
        deleteUrlTemplate: this.consumerDeleteUrlTemplateValue,
      });
    }

    async loadFoodItems() {
      await this.loadCategory("food", {
        listUrl: this.foodListUrlValue,
        tableBody: this.foodTableBodyTarget,
        loading: this.foodLoadingTarget,
        empty: this.foodEmptyTarget,
        summary: this.foodSummaryTarget,
        deleteUrlTemplate: this.foodDeleteUrlTemplateValue,
      });
    }

    async loadCategory(kind, refs) {
      if (!refs.listUrl) {
        return;
      }

      setVisible(refs.loading, true);
      setVisible(refs.empty, false);

      try {
        const { data } = await fetchJson(refs.listUrl);
        if (!data.success) {
          refs.tableBody.innerHTML = "";
          setVisible(refs.empty, true);
          refs.summary.textContent = "Ошибка загрузки";
          return;
        }

        const items = data.items || [];
        refs.summary.textContent = `Всего позиций: ${data.total || items.length}`;
        refs.tableBody.innerHTML = items
          .map((item) => this.renderRow(item, kind, refs.deleteUrlTemplate))
          .join("");
        setVisible(refs.empty, items.length === 0);
      } catch (error) {
        console.error(`Failed to load ${kind} positions`, error);
        refs.tableBody.innerHTML = "";
        setVisible(refs.empty, true);
        refs.summary.textContent = "Ошибка загрузки";
      } finally {
        setVisible(refs.loading, false);
      }
    }

    renderRow(item, kind, deleteUrlTemplate) {
      const position = escapeHtml(item.position);
      const deleteUrl = deleteUrlTemplate.replace("000", encodeURIComponent(item.position));
      const deleteAction =
        kind === "consumer"
          ? "click->special-sets#deleteConsumerPosition"
          : "click->special-sets#deleteFoodPosition";

      return `
        <tr>
          <td><code>${position}</code></td>
          <td class="text-end">${item.cargos_count ?? 0}</td>
          <td class="text-end">${item.routes_count ?? 0}</td>
          <td>
            <button
              type="button"
              class="btn btn-outline-danger btn-sm"
              data-position="${position}"
              data-delete-url="${escapeHtml(deleteUrl)}"
              data-action="${deleteAction}"
              title="Удалить позицию"
            >
              <i class="ti ti-trash"></i>
            </button>
          </td>
        </tr>
      `;
    }

    async addConsumerPosition() {
      await this.addPosition("consumer", {
        input: this.consumerPositionInputTarget,
        createUrl: this.consumerCreateUrlValue,
        errorsTarget: this.consumerCreateErrorsTarget,
        modalId: "addConsumerPositionModal",
        reload: () => this.loadConsumerItems(),
      });
    }

    async addFoodPosition() {
      await this.addPosition("food", {
        input: this.foodPositionInputTarget,
        createUrl: this.foodCreateUrlValue,
        errorsTarget: this.foodCreateErrorsTarget,
        modalId: "addFoodPositionModal",
        reload: () => this.loadFoodItems(),
      });
    }

    async addPosition(kind, refs) {
      const position = refs.input.value.trim();
      if (!position) {
        renderErrors(refs.errorsTarget, ["Укажите позицию"]);
        return;
      }

      try {
        const { data } = await fetchJson(refs.createUrl, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ position }),
        });

        if (!data.success) {
          renderErrors(refs.errorsTarget, data.errors || ["Ошибка сохранения"]);
          return;
        }

        refs.input.value = "";
        renderErrors(refs.errorsTarget, []);
        await this._closeModal(refs.modalId);
        await refs.reload();
        this._showRebuildToast();
      } catch (error) {
        console.error(`Failed to add ${kind} position`, error);
        renderErrors(refs.errorsTarget, ["Ошибка сети при сохранении"]);
      }
    }

    async deleteConsumerPosition(event) {
      await this.deletePosition(event, () => this.loadConsumerItems());
    }

    async deleteFoodPosition(event) {
      await this.deletePosition(event, () => this.loadFoodItems());
    }

    async deletePosition(event, reload) {
      const button = event.currentTarget;
      const position = button.dataset.position;
      const deleteUrl = button.dataset.deleteUrl;
      if (!position || !deleteUrl) {
        return;
      }

      const confirmed = window.confirm(
        `Удалить позицию ${position} из набора? Флаги грузов будут пересчитаны.`,
      );
      if (!confirmed) {
        return;
      }

      try {
        const { data } = await fetchJson(deleteUrl, { method: "POST" });
        if (!data.success) {
          window.alert((data.errors || ["Ошибка удаления"]).join("\n"));
          return;
        }
        await reload();
        this._showRebuildToast();
      } catch (error) {
        console.error("Failed to delete position", error);
        window.alert("Ошибка сети при удалении");
      }
    }

    _showRebuildToast() {
      showToast(
        "Данные обновляются в фоне. Расчёты эффектов будут готовы через несколько секунд.",
        {
          variant: "info",
          title: "Пересборка витрины",
        },
      );
    }
  }

  application.register("special-sets", SpecialSetsController);
})();
