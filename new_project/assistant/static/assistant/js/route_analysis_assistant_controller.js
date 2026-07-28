import { fetchJson } from "../../core/js/app/lib/http.js";
import { escapeHtml } from "../../core/js/app/lib/dom.js";

(function () {
  const application = window.stimulusApp;
  if (!application || typeof Stimulus === "undefined") {
    console.error(
      "Stimulus application is not initialized for route-analysis-assistant.",
    );
    return;
  }

  class RouteAnalysisAssistantController extends Stimulus.Controller {
    static targets = [
      "messages",
      "input",
      "sendButton",
      "errors",
      "statusBadge",
      "presets",
    ];

    static values = {
      chatUrl: String,
    };

    connect() {
      this.pageContext = {
        scenarioId: null,
        routeId: null,
        overrides: null,
        snapshot: null,
        routeCode: null,
      };
      this.history = [];
      this.loading = false;
      this._onContextUpdated = this._onContextUpdated.bind(this);
      document.addEventListener(
        "route-analysis:context-updated",
        this._onContextUpdated,
      );
      this._syncEnabled();
    }

    disconnect() {
      document.removeEventListener(
        "route-analysis:context-updated",
        this._onContextUpdated,
      );
    }

    _onContextUpdated(event) {
      const detail = event.detail || {};
      this.pageContext = {
        scenarioId: detail.scenarioId ?? null,
        routeId: detail.routeId ?? (detail.route && detail.route.id) ?? null,
        overrides: detail.overrides || null,
        snapshot: detail.snapshot || null,
        routeCode:
          (detail.route && detail.route.route_code) ||
          (detail.snapshot && detail.snapshot.route_code) ||
          null,
      };
      this._syncEnabled();
    }

    _syncEnabled() {
      const ready = Boolean(
        this.pageContext &&
          this.pageContext.scenarioId &&
          this.pageContext.routeId,
      );
      const disabled = !ready || this.loading;

      // Прямой DOM — не зависим от Stimulus targets (и не трогаем this.context).
      this.element
        .querySelectorAll("button[data-preset]")
        .forEach((btn) => {
          btn.disabled = disabled;
        });
      const input = this.element.querySelector(
        '[data-route-analysis-assistant-target="input"]',
      );
      if (input) input.disabled = disabled;
      const sendButton = this.element.querySelector(
        '[data-route-analysis-assistant-target="sendButton"]',
      );
      if (sendButton) sendButton.disabled = disabled;

      const badge = this.element.querySelector(
        '[data-route-analysis-assistant-target="statusBadge"]',
      );
      if (badge) {
        if (!ready) {
          badge.textContent = "Выберите маршрут";
          badge.className = "badge bg-secondary-lt";
        } else if (this.loading) {
          badge.textContent = "Думаю…";
          badge.className = "badge bg-azure-lt";
        } else {
          const code =
            this.pageContext.routeCode || `#${this.pageContext.routeId}`;
          badge.textContent = `Маршрут ${code}`;
          badge.className = "badge bg-green-lt";
        }
      }
    }

    onPreset(event) {
      const button = event.currentTarget;
      const preset = button && button.getAttribute("data-preset");
      if (!preset) return;
      const label = (button.textContent || preset).trim();
      this._send({ preset, userLabel: label });
    }

    onSubmit(event) {
      event.preventDefault();
      const message = (this.inputTarget.value || "").trim();
      if (!message) return;
      this.inputTarget.value = "";
      this._send({ message, userLabel: message });
    }

    async _send({ message = null, preset = null, userLabel }) {
      if (this.loading) return;
      if (!this.pageContext.scenarioId || !this.pageContext.routeId) {
        this._showErrors(["Сначала выберите сценарий и маршрут."]);
        return;
      }
      if (!this.chatUrlValue) {
        this._showErrors(["URL чата не задан."]);
        return;
      }

      this._showErrors([]);
      this._appendMessage("user", userLabel);
      this.loading = true;
      this._syncEnabled();

      const body = {
        page: "route_analysis",
        message: message || "",
        preset: preset || null,
        context: {
          scenario_id: Number(this.pageContext.scenarioId),
          route_id: Number(this.pageContext.routeId),
          overrides: this.pageContext.overrides || {},
        },
        history: this.history.slice(-8),
      };

      try {
        const { data } = await fetchJson(this.chatUrlValue, {
          method: "POST",
          body,
        });
        if (!data || !data.success) {
          const errors = (data && data.errors) || ["Ошибка ассистента"];
          this._showErrors(errors);
          this._appendMessage("assistant", errors.join("\n"));
          return;
        }
        const answer = data.answer || "";
        this._appendMessage("assistant", answer);
        if (message) {
          this.history.push({ role: "user", content: message });
          this.history.push({ role: "assistant", content: answer });
        }
      } catch (err) {
        this._showErrors([String(err && err.message ? err.message : err)]);
      } finally {
        this.loading = false;
        this._syncEnabled();
      }
    }

    _appendMessage(role, text) {
      if (!this.hasMessagesTarget) return;
      const emptyHint = this.messagesTarget.querySelector(".text-muted.small");
      if (emptyHint) emptyHint.remove();

      const item = document.createElement("div");
      item.className = `route-analysis-assistant__msg route-analysis-assistant__msg--${role}`;
      const roleLabel = role === "user" ? "Вы" : "Ассистент";
      item.innerHTML = `
        <div class="route-analysis-assistant__msg-role">${escapeHtml(roleLabel)}</div>
        <div class="route-analysis-assistant__msg-body">${this._formatAnswer(text)}</div>
      `;
      this.messagesTarget.appendChild(item);
      this.messagesTarget.scrollTop = this.messagesTarget.scrollHeight;
    }

    _formatAnswer(text) {
      const raw = String(text || "");
      // Простой markdown: **bold**, переносы строк, заголовки ###
      let html = escapeHtml(raw);
      html = html.replace(/^###\s+(.+)$/gm, "<strong>$1</strong>");
      html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      html = html.replace(/\n/g, "<br>");
      return html;
    }

    _showErrors(errors) {
      if (!this.hasErrorsTarget) return;
      if (!errors || !errors.length) {
        this.errorsTarget.style.display = "none";
        this.errorsTarget.textContent = "";
        return;
      }
      this.errorsTarget.style.display = "";
      this.errorsTarget.textContent = errors.join(" ");
    }
  }

  application.register(
    "route-analysis-assistant",
    RouteAnalysisAssistantController,
  );
})();
