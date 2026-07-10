function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

const FAST_POLL_MS = 300;
const COMPACT_POLL_MS = 2000;
const DONE_POLL_MS = 30000;

export class DecisionEffectsPipeline {
  constructor({ statusUrl, fetchJson }) {
    this.statusUrl = statusUrl;
    this.fetchJson = fetchJson;
    this.generation = 0;
    this.filterGeneration = 0;
    this.scenarioId = null;
    this.cacheKey = null;
    this.clientDataVersion = null;
    this.lastStage = null;
    this.stopped = true;
    this.computing = false;
    this.computeTriggered = false;
    this.onStageChange = null;
    this.abortController = new AbortController();
  }

  start(scenarioId, { cacheKey = null, clientDataVersion = null } = {}) {
    this.stop({ resetGeneration: false });
    this.generation += 1;
    this.scenarioId = scenarioId;
    this.cacheKey = cacheKey;
    this.clientDataVersion = clientDataVersion;
    this.lastStage = null;
    this.stopped = false;
    this.computing = false;
    this.computeTriggered = false;
    this.abortController = new AbortController();
    const gen = this.generation;
    void this._pollLoop(gen);
    return gen;
  }

  stop({ resetGeneration = true } = {}) {
    this.stopped = true;
    if (this.abortController) {
      this.abortController.abort();
    }
    if (resetGeneration) {
      this.generation += 1;
    }
  }

  restart() {
    return this.start(this.scenarioId, {
      cacheKey: null,
      clientDataVersion: this.clientDataVersion,
    });
  }

  setCacheKey(cacheKey, clientDataVersion = null) {
    this.cacheKey = cacheKey || null;
    if (clientDataVersion) {
      this.clientDataVersion = clientDataVersion;
    }
  }

  setClientDataVersion(clientDataVersion) {
    this.clientDataVersion = clientDataVersion || null;
  }

  setComputing(value) {
    this.computing = Boolean(value);
    if (!value) {
      this.computeTriggered = false;
    }
  }

  markComputeTriggered() {
    this.computeTriggered = true;
  }

  bumpFilterGeneration() {
    this.filterGeneration += 1;
    if (this.abortController) {
      this.abortController.abort();
      this.abortController = new AbortController();
    }
    return this.filterGeneration;
  }

  isCurrent(gen) {
    return gen === this.generation;
  }

  isFilterCurrent(filterGen) {
    return filterGen === this.filterGeneration;
  }

    getSignal() {
      return this.abortController?.signal;
    }

    pollNow() {
      if (this.stopped || !this.scenarioId) {
        return;
      }
      const gen = this.generation;
      void this._fetchStatus(gen).then((status) => {
        if (!this.stopped && this.isCurrent(gen) && status) {
          void this._handleStatus(status, gen);
        }
      });
    }

    _pollInterval(stage) {
    if (stage === "mart_rebuilding" || stage === "scenario_warming") {
      return FAST_POLL_MS;
    }
    if (stage === "compact_pending" || stage === "fallout_pending") {
      return COMPACT_POLL_MS;
    }
    if (stage === "done") {
      return DONE_POLL_MS;
    }
    return FAST_POLL_MS;
  }

  async _pollLoop(gen) {
    while (!this.stopped && this.isCurrent(gen)) {
      const status = await this._fetchStatus(gen);
      if (!this.stopped && this.isCurrent(gen) && status) {
        await this._handleStatus(status, gen);
      }
      if (this.stopped || !this.isCurrent(gen)) {
        break;
      }
      const stage = status?.stage || this.lastStage || "ready_for_compute";
      await sleep(this._pollInterval(stage));
    }
  }

  async _fetchStatus(gen) {
    if (!this.statusUrl || !this.scenarioId) {
      return null;
    }

    const params = new URLSearchParams({
      scenario_id: String(this.scenarioId),
    });
    if (this.cacheKey) {
      params.set("cache_key", this.cacheKey);
    }
    if (this.clientDataVersion) {
      params.set("client_data_version", this.clientDataVersion);
    }

    try {
      const { data } = await this.fetchJson(`${this.statusUrl}?${params.toString()}`, {
        signal: this.getSignal(),
      });
      if (!data || !data.success || !this.isCurrent(gen)) {
        return null;
      }
      return data;
    } catch (error) {
      if (error?.name === "AbortError") {
        return null;
      }
      console.error("[decision-effects-pipeline] status poll failed", error);
      return null;
    }
  }

  async _handleStatus(status, gen) {
    const stage = status.stage;
    const stageChanged = stage !== this.lastStage;

    if (
      status.data_version_changed &&
      (stage === "done" || stage === "ready_for_compute") &&
      this.cacheKey &&
      !this.computing
    ) {
      this.lastStage = null;
      this.cacheKey = null;
      if (this.onStageChange) {
        await this.onStageChange("data_version_changed", status, gen);
      }
      return;
    }

    if (stage === "ready_for_compute" && this.computing) {
      return;
    }

    if (stage === "ready_for_compute" && this.computeTriggered) {
      return;
    }

    if (!stageChanged) {
      return;
    }

    this.lastStage = stage;
    if (this.onStageChange) {
      await this.onStageChange(stage, status, gen);
    }
  }
}
