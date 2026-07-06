import { fetchJson } from "../lib/http.js";
import { escapeHtml, setVisible } from "../lib/dom.js";
import { renderErrors } from "../lib/errors.js";

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
      this.loadConsumerItems();
      this.loadFoodItems();
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
        const modalEl = document.getElementById(refs.modalId);
        if (modalEl && window.bootstrap) {
          const modal = window.bootstrap.Modal.getInstance(modalEl);
          if (modal) {
            modal.hide();
          }
        }
        await refs.reload();
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
      } catch (error) {
        console.error("Failed to delete position", error);
        window.alert("Ошибка сети при удалении");
      }
    }
  }

  application.register("special-sets", SpecialSetsController);
})();
