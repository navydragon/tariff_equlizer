import { showToast } from "../../core/js/app/lib/toast.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for task-detail.");
    return;
  }

  class TaskDetailController extends Stimulus.Controller {
    static targets = [
      "descriptionInput",
      "statusSelect",
      "prioritySelect",
      "typeSelect",
      "deadlineInput",
      "assigneeSelect",
      "scenarioSelect",
      "commentsPanel",
      "activityPanel",
      "commentsList",
      "commentInput",
      "attachmentsList",
      "noAttachments",
      "fileInput",
      "watchLabel",
      "toastContainer",
    ];

    static values = {
      taskId: Number,
      apiUrl: String,
      commentsUrl: String,
      attachmentsUrl: String,
      watchUrl: String,
      listUrl: String,
    };

    connect() {
      this.loadReferenceData();
    }

    toastOptions() {
      const options = { delay: 5000 };
      if (this.hasToastContainerTarget) {
        options.container = this.toastContainerTarget;
      }
      return options;
    }

    notifySuccess(message) {
      showToast(message, { variant: "success", ...this.toastOptions() });
    }

    notifyError(errors) {
      const messages = Array.isArray(errors) ? errors : [errors || "Ошибка"];
      showToast(messages, { variant: "error", ...this.toastOptions() });
    }

    async loadReferenceData() {
      try {
        const [usersRes, scenariosRes, taskRes] = await Promise.all([
          fetch("/support/api/users/"),
          fetch("/support/api/scenarios/"),
          fetch(this.apiUrlValue),
        ]);
        const usersData = await usersRes.json();
        const scenariosData = await scenariosRes.json();
        const taskData = await taskRes.json();
        if (usersData.success) {
          usersData.users.forEach((u) => {
            const opt = document.createElement("option");
            opt.value = u.id;
            opt.textContent = u.name || u.login;
            if (taskData.success && taskData.task.assignee_id === u.id) {
              opt.selected = true;
            }
            this.assigneeSelectTarget.appendChild(opt);
          });
        }
        if (scenariosData.success) {
          scenariosData.scenarios.forEach((s) => {
            const opt = document.createElement("option");
            opt.value = s.id;
            opt.textContent = s.name;
            if (taskData.success && taskData.task.scenario_id === s.id) {
              opt.selected = true;
            }
            this.scenarioSelectTarget.appendChild(opt);
          });
        }
      } catch (e) {
        console.error("Failed to load reference data", e);
      }
    }

    csrfToken() {
      const cookie = document.cookie
        .split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith("csrftoken="));
      return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
    }

    async patchTask(payload) {
      const res = await fetch(this.apiUrlValue, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": this.csrfToken(),
        },
        body: JSON.stringify(payload),
      });
      return res.json();
    }

    async applyPatch(payload, successMessage) {
      try {
        const data = await this.patchTask(payload);
        if (data.success) {
          this.notifySuccess(successMessage);
          return data;
        }
        this.notifyError(data.errors);
        return data;
      } catch (e) {
        this.notifyError("Не удалось сохранить изменения");
        return { success: false };
      }
    }

    async saveDescription() {
      await this.applyPatch(
        { description: this.descriptionInputTarget.value },
        "Описание сохранено",
      );
    }

    async saveField() {
      await this.applyPatch(
        {
          status: this.statusSelectTarget.value,
          priority: this.prioritySelectTarget.value,
          task_type: this.typeSelectTarget.value,
        },
        "Параметры задачи обновлены",
      );
    }

    async saveDeadline() {
      const value = this.deadlineInputTarget.value;
      if (value) {
        await this.applyPatch({ deadline: value }, "Дедлайн обновлён");
      } else {
        await this.applyPatch({ clear_deadline: true }, "Дедлайн снят");
      }
    }

    async saveAssignee() {
      const value = this.assigneeSelectTarget.value;
      if (value) {
        await this.applyPatch(
          { assignee_id: parseInt(value, 10) },
          "Исполнитель назначен",
        );
      } else {
        await this.applyPatch({ clear_assignee: true }, "Исполнитель снят");
      }
    }

    async saveScenario() {
      const value = this.scenarioSelectTarget.value;
      if (value) {
        await this.applyPatch(
          { scenario_id: parseInt(value, 10) },
          "Сценарий привязан",
        );
      } else {
        await this.applyPatch({ clear_scenario: true }, "Сценарий отвязан");
      }
    }

    showComments(event) {
      event.preventDefault();
      this.commentsPanelTarget.style.display = "";
      this.activityPanelTarget.style.display = "none";
    }

    showActivity(event) {
      event.preventDefault();
      this.commentsPanelTarget.style.display = "none";
      this.activityPanelTarget.style.display = "";
    }

    appendComment(comment) {
      const emptyMsg = this.commentsListTarget.querySelector(".text-muted");
      if (emptyMsg) emptyMsg.remove();

      const block = document.createElement("div");
      block.className = "mb-3 pb-3 border-bottom";
      block.innerHTML = `
        <div class="d-flex justify-content-between">
          <strong>${this.escapeHtml(comment.author_name)}</strong>
          <span class="text-muted small">${this.escapeHtml(comment.created_at)}</span>
        </div>
        <div class="mt-1">${this.escapeHtml(comment.body).replace(/\n/g, "<br>")}</div>
      `;
      this.commentsListTarget.appendChild(block);
    }

    async addComment(event) {
      event.preventDefault();
      const body = this.commentInputTarget.value.trim();
      if (!body) return;

      try {
        const res = await fetch(this.commentsUrlValue, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": this.csrfToken(),
          },
          body: JSON.stringify({ body }),
        });
        const data = await res.json();
        if (data.success) {
          this.appendComment(data.comment);
          this.commentInputTarget.value = "";
          this.notifySuccess("Комментарий добавлен");
        } else {
          this.notifyError(data.errors);
        }
      } catch (e) {
        this.notifyError("Не удалось добавить комментарий");
      }
    }

    appendAttachment(attachment) {
      if (this.hasNoAttachmentsTarget) {
        this.noAttachmentsTarget.remove();
      }

      const row = document.createElement("div");
      row.className = "d-flex justify-content-between align-items-center mb-2";
      row.dataset.attachmentId = attachment.id;
      row.innerHTML = `
        <a href="${this.escapeHtml(attachment.url)}" target="_blank">${this.escapeHtml(attachment.original_name)}</a>
        <div>
          <span class="text-muted small me-2">${this.escapeHtml(attachment.uploaded_by_name)}</span>
          <button class="btn btn-sm btn-outline-danger" data-action="click->task-detail#deleteAttachment" data-attachment-id="${attachment.id}">×</button>
        </div>
      `;
      this.attachmentsListTarget.appendChild(row);
    }

    async uploadAttachment(event) {
      event.preventDefault();
      const file = this.fileInputTarget.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append("file", file);
      try {
        const res = await fetch(this.attachmentsUrlValue, {
          method: "POST",
          headers: { "X-CSRFToken": this.csrfToken() },
          body: formData,
        });
        const data = await res.json();
        if (data.success) {
          this.appendAttachment(data.attachment);
          this.fileInputTarget.value = "";
          this.notifySuccess("Файл загружен");
        } else {
          this.notifyError(data.errors);
        }
      } catch (e) {
        this.notifyError("Не удалось загрузить файл");
      }
    }

    async deleteAttachment(event) {
      const id = event.currentTarget.dataset.attachmentId;
      if (!confirm("Удалить вложение?")) return;
      try {
        const res = await fetch(`/support/api/attachments/${id}/`, {
          method: "DELETE",
          headers: { "X-CSRFToken": this.csrfToken() },
        });
        const data = await res.json();
        if (data.success) {
          event.currentTarget.closest("[data-attachment-id]").remove();
          this.notifySuccess("Вложение удалено");
        } else {
          this.notifyError(data.errors);
        }
      } catch (e) {
        this.notifyError("Не удалось удалить вложение");
      }
    }

    async toggleWatch() {
      try {
        const res = await fetch(this.watchUrlValue, {
          method: "POST",
          headers: { "X-CSRFToken": this.csrfToken() },
        });
        const data = await res.json();
        if (data.success) {
          this.watchLabelTarget.textContent = data.is_watching ? "Отписаться" : "Следить";
          this.notifySuccess(
            data.is_watching ? "Вы подписаны на задачу" : "Подписка отменена",
          );
        } else {
          this.notifyError(data.errors);
        }
      } catch (e) {
        this.notifyError("Не удалось изменить подписку");
      }
    }

    async deleteTask() {
      if (!confirm("Удалить задачу?")) return;
      try {
        const res = await fetch(this.apiUrlValue, {
          method: "DELETE",
          headers: { "X-CSRFToken": this.csrfToken() },
        });
        const data = await res.json();
        if (data.success) {
          this.notifySuccess("Задача удалена");
          setTimeout(() => {
            window.location.href = this.listUrlValue;
          }, 600);
        } else {
          this.notifyError(data.errors || ["Нет прав"]);
        }
      } catch (e) {
        this.notifyError("Не удалось удалить задачу");
      }
    }

    escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text || "";
      return div.innerHTML;
    }
  }

  application.register("task-detail", TaskDetailController);
})();
