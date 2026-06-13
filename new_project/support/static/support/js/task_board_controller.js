(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error("Stimulus application is not initialized for task-board.");
    return;
  }

  const PRIORITY_BADGES = {
    low: "bg-secondary-lt",
    medium: "bg-blue-lt",
    high: "bg-orange-lt",
    urgent: "bg-red-lt",
  };

  const STATUS_BADGES = {
    backlog: "bg-secondary-lt",
    open: "bg-azure-lt",
    in_progress: "bg-yellow-lt",
    review: "bg-purple-lt",
    done: "bg-green-lt",
    cancelled: "bg-dark-lt",
  };

  class TaskBoardController extends Stimulus.Controller {
    static targets = [
      "stats",
      "searchInput",
      "scopeSelect",
      "statusSelect",
      "prioritySelect",
      "typeSelect",
      "overdueCheck",
      "unassignedCheck",
      "loading",
      "tableView",
      "tableBody",
      "tableEmpty",
      "kanbanView",
      "viewTableBtn",
      "viewKanbanBtn",
      "createForm",
      "createError",
      "assigneeSelect",
      "scenarioSelect",
    ];

    static values = {
      listUrl: String,
      statusUrlTemplate: String,
      tagsUrl: String,
      usersUrl: String,
      scenariosUrl: String,
      detailUrlTemplate: String,
      kanbanStatuses: Array,
      statusLabels: Object,
    };

    connect() {
      this.currentView = "table";
      this.debounceTimer = null;
      this.loadReferenceData();
      this.loadTasks();
    }

    async loadReferenceData() {
      try {
        const [usersRes, scenariosRes] = await Promise.all([
          fetch(this.usersUrlValue),
          fetch(this.scenariosUrlValue),
        ]);
        const usersData = await usersRes.json();
        const scenariosData = await scenariosRes.json();
        if (usersData.success && this.hasAssigneeSelectTarget) {
          usersData.users.forEach((u) => {
            const opt = document.createElement("option");
            opt.value = u.id;
            opt.textContent = u.name || u.login;
            this.assigneeSelectTarget.appendChild(opt);
          });
        }
        if (scenariosData.success && this.hasScenarioSelectTarget) {
          scenariosData.scenarios.forEach((s) => {
            const opt = document.createElement("option");
            opt.value = s.id;
            opt.textContent = s.name;
            this.scenarioSelectTarget.appendChild(opt);
          });
        }
      } catch (e) {
        console.error("Failed to load reference data", e);
      }
    }

    debouncedLoad() {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = setTimeout(() => this.loadTasks(), 300);
    }

    showTable() {
      this.currentView = "table";
      this.tableViewTarget.style.display = "";
      this.kanbanViewTarget.style.display = "none";
      this.viewTableBtnTarget.classList.add("active");
      this.viewKanbanBtnTarget.classList.remove("active");
    }

    showKanban() {
      this.currentView = "kanban";
      this.tableViewTarget.style.display = "none";
      this.kanbanViewTarget.style.display = "";
      this.viewKanbanBtnTarget.classList.add("active");
      this.viewTableBtnTarget.classList.remove("active");
      this.renderKanban();
    }

    buildQueryParams() {
      const params = new URLSearchParams();
      params.set("scope", this.scopeSelectTarget.value);
      if (this.searchInputTarget.value.trim()) {
        params.set("search", this.searchInputTarget.value.trim());
      }
      if (this.statusSelectTarget.value) params.set("status", this.statusSelectTarget.value);
      if (this.prioritySelectTarget.value) params.set("priority", this.prioritySelectTarget.value);
      if (this.typeSelectTarget.value) params.set("task_type", this.typeSelectTarget.value);
      if (this.overdueCheckTarget.checked) params.set("overdue_only", "true");
      if (this.unassignedCheckTarget.checked) params.set("unassigned_only", "true");
      return params;
    }

    async loadTasks() {
      this.loadingTarget.style.display = "";
      try {
        const res = await fetch(`${this.listUrlValue}?${this.buildQueryParams()}`);
        const data = await res.json();
        if (!data.success) return;
        this.tasks = data.tasks;
        this.updateStats(data.stats);
        this.renderTable();
        if (this.currentView === "kanban") this.renderKanban();
      } catch (e) {
        console.error("Failed to load tasks", e);
      } finally {
        this.loadingTarget.style.display = "none";
      }
    }

    updateStats(stats) {
      if (!this.hasStatsTarget) return;
      Object.entries(stats).forEach(([key, value]) => {
        const el = this.statsTarget.querySelector(`[data-stat="${key}"]`);
        if (el) el.textContent = value;
      });
    }

    taskDetailUrl(id) {
      return this.detailUrlTemplateValue.replace("/0/", `/${id}/`);
    }

    renderTable() {
      const tasks = this.tasks || [];
      this.tableBodyTarget.innerHTML = "";
      if (tasks.length === 0) {
        this.tableEmptyTarget.style.display = "";
        return;
      }
      this.tableEmptyTarget.style.display = "none";
      tasks.forEach((task) => {
        const tr = document.createElement("tr");
        const deadlineClass = task.is_overdue ? "text-danger fw-bold" : "";
        tr.innerHTML = `
          <td>${task.id}</td>
          <td><a href="${this.taskDetailUrl(task.id)}">${this.escapeHtml(task.title)}</a></td>
          <td><span class="badge ${STATUS_BADGES[task.status] || ""}">${this.escapeHtml(task.status_label)}</span></td>
          <td><span class="badge ${PRIORITY_BADGES[task.priority] || ""}">${this.escapeHtml(task.priority_label)}</span></td>
          <td>${this.escapeHtml(task.author_name)}</td>
          <td>${this.escapeHtml(task.assignee_name || "—")}</td>
          <td class="${deadlineClass}">${this.escapeHtml(task.deadline || "—")}</td>
          <td>${this.escapeHtml(task.updated_at)}</td>
        `;
        this.tableBodyTarget.appendChild(tr);
      });
    }

    renderKanban() {
      const tasks = this.tasks || [];
      const statuses = this.kanbanStatusesValue;
      const labels = this.statusLabelsValue;
      this.kanbanViewTarget.innerHTML = "";

      const row = document.createElement("div");
      row.className = "row flex-nowrap g-3";

      statuses.forEach((status) => {
        const col = document.createElement("div");
        col.className = "col-10 col-sm-8 col-md-6 col-lg kanban-col";
        col.innerHTML = `
          <div class="card h-100">
            <div class="card-header py-2">
              <h3 class="card-title mb-0">${this.escapeHtml(labels[status] || status)}</h3>
            </div>
            <div class="card-body p-2 kanban-column" data-kanban-status="${status}"
                 data-action="dragover->task-board#allowDrop drop->task-board#handleDrop">
            </div>
          </div>
        `;
        row.appendChild(col);
      });

      this.kanbanViewTarget.appendChild(row);

      tasks.forEach((task) => {
        const column = row.querySelector(
          `.kanban-column[data-kanban-status="${task.status}"]`
        );
        if (!column) return;
        const card = document.createElement("div");
        card.className = "card card-sm mb-2";
        card.draggable = true;
        card.dataset.taskId = task.id;
        card.dataset.action = "dragstart->task-board#handleDragStart";
        const deadlineClass = task.is_overdue ? "text-danger" : "text-muted";
        card.innerHTML = `
          <div class="card-body p-2">
            <div class="d-flex justify-content-between">
              <a href="${this.taskDetailUrl(task.id)}" class="fw-bold text-truncate">${this.escapeHtml(task.title)}</a>
              <span class="badge ${PRIORITY_BADGES[task.priority] || ""}">${this.escapeHtml(task.priority_label)}</span>
            </div>
            <div class="text-muted small">#${task.id} · ${this.escapeHtml(task.author_name)}</div>
            <div class="small ${deadlineClass}">${task.deadline ? this.escapeHtml(task.deadline) : ""}</div>
          </div>
        `;
        column.appendChild(card);
      });
    }

    handleDragStart(event) {
      event.dataTransfer.setData("text/plain", event.currentTarget.dataset.taskId);
      event.dataTransfer.effectAllowed = "move";
    }

    allowDrop(event) {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    }

    async handleDrop(event) {
      event.preventDefault();
      const taskId = event.dataTransfer.getData("text/plain");
      const newStatus = event.currentTarget.dataset.kanbanStatus;
      if (!taskId || !newStatus) return;

      const url = this.statusUrlTemplateValue.replace("/0/", `/${taskId}/`);
      try {
        const res = await fetch(url, {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": this.csrfToken(),
          },
          body: JSON.stringify({ status: newStatus }),
        });
        const data = await res.json();
        if (data.success) {
          await this.loadTasks();
        }
      } catch (e) {
        console.error("Failed to update status", e);
      }
    }

    openCreateModal() {
      const modalEl = document.getElementById("createTaskModal");
      if (!modalEl) return;
      if (this.hasCreateErrorTarget) {
        this.createErrorTarget.style.display = "none";
      }
      if (this.hasCreateFormTarget) {
        this.createFormTarget.reset();
      }
      bootstrap.Modal.getOrCreateInstance(modalEl).show();
    }

    async createTask(event) {
      event.preventDefault();
      const form = this.createFormTarget;
      const formData = new FormData(form);
      const payload = {
        title: formData.get("title"),
        description: formData.get("description") || "",
        priority: formData.get("priority"),
        task_type: formData.get("task_type"),
        deadline: formData.get("deadline") || null,
        assignee_id: formData.get("assignee_id") || null,
        scenario_id: formData.get("scenario_id") || null,
      };

      try {
        const res = await fetch(this.listUrlValue, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": this.csrfToken(),
          },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!data.success) {
          this.createErrorTarget.textContent = (data.errors || ["Ошибка"]).join(", ");
          this.createErrorTarget.style.display = "";
          return;
        }
        bootstrap.Modal.getInstance(document.getElementById("createTaskModal")).hide();
        window.location.href = this.taskDetailUrl(data.task.id);
      } catch (e) {
        this.createErrorTarget.textContent = "Ошибка при создании задачи";
        this.createErrorTarget.style.display = "";
      }
    }

    csrfToken() {
      const cookie = document.cookie
        .split(";")
        .map((c) => c.trim())
        .find((c) => c.startsWith("csrftoken="));
      return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
    }

    escapeHtml(text) {
      const div = document.createElement("div");
      div.textContent = text || "";
      return div.innerHTML;
    }
  }

  application.register("task-board", TaskBoardController);
})();
