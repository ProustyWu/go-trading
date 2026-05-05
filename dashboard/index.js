const THEME_STORAGE_KEY = "gs-ai-trader-theme";

const els = {
  workbenchMeta: document.querySelector("#workbenchMeta"),
  workbenchSummary: document.querySelector("#workbenchSummary"),
  instanceGrid: document.querySelector("#instanceGrid"),
  familyGrid: document.querySelector("#familyGrid"),
  evolutionMeta: document.querySelector("#evolutionMeta"),
  createPaperBtn: document.querySelector("#createPaperBtn"),
  createLiveBtn: document.querySelector("#createLiveBtn"),
  createFamilyBtn: document.querySelector("#createFamilyBtn"),
  refreshWorkbenchBtn: document.querySelector("#refreshWorkbenchBtn")
};

const state = {
  payload: null,
  evolution: null,
  filter: "all"
};

function readStoredTheme() {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) || "dark";
  } catch {
    return "dark";
  }
}

function applyTheme() {
  document.documentElement.dataset.theme = readStoredTheme() === "light" ? "light" : "dark";
}

function fmtUsd(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "$0";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(num);
}

function fmtScore(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "n/a";
  return num.toFixed(2);
}

function fmtDateTime(value) {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "n/a";
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
}

function fmtDurationSeconds(value) {
  const seconds = Math.max(0, Math.ceil(Number(value) || 0));
  const minutes = Math.floor(seconds / 60);
  const rest = seconds % 60;
  if (minutes <= 0) return `${rest} 秒`;
  return `${minutes} 分 ${rest} 秒`;
}

function fmtOptionalDuration(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "n/a";
  return fmtDurationSeconds(num);
}

function cooldownText(cooldown) {
  if (!cooldown || !cooldown.active) return "";
  const exchange = String(cooldown.exchange || "binance").toUpperCase();
  const until = fmtDateTime(cooldown.untilAt);
  const remaining = fmtDurationSeconds(cooldown.remainingSeconds);
  return `${exchange} API 冷却中，预计到 ${until}，剩余 ${remaining}`;
}

function renderCooldownNotice(cooldown, className = "exchange-cooldown-banner") {
  const text = cooldownText(cooldown);
  if (!text) return "";
  const reason = cooldown.reason ? ` · ${cooldown.reason}` : "";
  return `<div class="${className}"><strong>${escapeHtml(text)}</strong><span>${escapeHtml(reason)}</span></div>`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${response.status} ${response.statusText}`);
  return payload;
}

async function postJson(url, body = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.error || `${response.status} ${response.statusText}`);
  return payload;
}

function visibleInstances() {
  const instances = state.payload?.instances || [];
  if (state.filter === "paper") return instances.filter((item) => item.type === "paper");
  if (state.filter === "live") return instances.filter((item) => item.type === "live");
  if (state.filter === "running") return instances.filter((item) => item.running);
  return instances;
}

function buildSparklineSvg(points) {
  const dataset = (Array.isArray(points) ? points : [])
    .map((item) => ({
      at: item?.at || null,
      equityUsd: Number(item?.equityUsd)
    }))
    .filter((item) => Number.isFinite(item.equityUsd));
  const values = dataset
    .map((item) => item.equityUsd)
    .filter((item) => Number.isFinite(item));
  if (!values.length) {
    return `<div class="instance-sparkline-empty">暂无曲线</div>`;
  }
  const width = 320;
  const height = 156;
  const padding = 8;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const flat = max === min;
  const span = flat ? 1 : (max - min);
  const coords = values.map((value, index) => {
    const x = padding + ((width - padding * 2) * index) / Math.max(1, values.length - 1);
    const y = flat
      ? height / 2
      : height - padding - ((value - min) / span) * (height - padding * 2);
    return { x, y };
  });
  const path = coords.map((point, index) => `${index === 0 ? "M" : "L"}${point.x.toFixed(2)},${point.y.toFixed(2)}`).join(" ");
  const fillPath = `${path} L${coords.at(-1).x.toFixed(2)},${(height - padding).toFixed(2)} L${coords[0].x.toFixed(2)},${(height - padding).toFixed(2)} Z`;
  const startPoint = coords[0];
  const endPoint = coords.at(-1);
  return `
    <svg viewBox="0 0 ${width} ${height}" class="instance-sparkline" preserveAspectRatio="none" aria-hidden="true">
      <path d="${fillPath}" class="instance-sparkline-fill"></path>
      <path d="${path}" class="instance-sparkline-line"></path>
      <circle cx="${startPoint.x.toFixed(2)}" cy="${startPoint.y.toFixed(2)}" r="4" class="instance-sparkline-dot is-start"></circle>
      <circle cx="${endPoint.x.toFixed(2)}" cy="${endPoint.y.toFixed(2)}" r="4.5" class="instance-sparkline-dot is-end"></circle>
    </svg>
  `;
}

function renderWorkbench() {
  const instances = state.payload?.instances || [];
  const runningCount = instances.filter((item) => item.running).length;
  const paperCount = instances.filter((item) => item.type === "paper").length;
  const liveCount = instances.filter((item) => item.type === "live").length;
  const activeCooldowns = Object.values(state.payload?.exchangeCooldowns || {}).filter((item) => item?.active);
  els.workbenchMeta.textContent = activeCooldowns.length ? activeCooldowns.map(cooldownText).filter(Boolean).join("；") : "";
  els.workbenchSummary.innerHTML = `
    <article class="workbench-summary-card ${state.filter === "all" ? "active" : ""}" data-filter-id="all">
      <span>全部</span>
      <strong>${instances.length}</strong>
    </article>
    <article class="workbench-summary-card ${state.filter === "paper" ? "active" : ""}" data-filter-id="paper">
      <span>模拟盘</span>
      <strong>${paperCount}</strong>
    </article>
    <article class="workbench-summary-card ${state.filter === "live" ? "active" : ""}" data-filter-id="live">
      <span>实盘</span>
      <strong>${liveCount}</strong>
    </article>
    <article class="workbench-summary-card ${state.filter === "running" ? "active" : ""}" data-filter-id="running">
      <span>运行中</span>
      <strong>${runningCount}</strong>
    </article>
  `;
  const cards = visibleInstances();
  els.instanceGrid.innerHTML = cards.map((instance) => `
    <article class="instance-card">
      <div class="instance-card-top">
        <div>
          <p class="instance-type">${escapeHtml(instance.type.toUpperCase())}</p>
          <h2>${escapeHtml(instance.name)}</h2>
          <p class="meta">交易所 ${escapeHtml(instance.exchange || "binance")} · ${escapeHtml(instance.running ? "已启动" : "已暂停")}</p>
        </div>
        <div class="instance-status-indicator ${instance.running ? "is-running" : "is-stopped"}" aria-label="${escapeHtml(instance.running ? "已启动" : "已暂停")}" title="${escapeHtml(instance.running ? "已启动" : "已暂停")}"></div>
      </div>
      <div class="instance-stats-grid">
        <span>Equity <strong>${escapeHtml(fmtUsd(instance.equityUsd))}</strong></span>
        <span>Open <strong>${escapeHtml(String(instance.openPositions || 0))}</strong></span>
        <span>候选池 <strong>${escapeHtml(String(instance.candidateUniverseSize || 0))}</strong></span>
        <span>下次调度 <strong>${escapeHtml(fmtDateTime(instance.nextDecisionDueAt))}</strong></span>
      </div>
      <div class="instance-chart-block">
        <div class="instance-chart-head">
          <span>Equity Curve</span>
          <strong>${escapeHtml(fmtUsd(instance.equityUsd))}</strong>
        </div>
        ${buildSparklineSvg(instance.equityCurve)}
      </div>
      <p class="meta">最近决策 ${escapeHtml(fmtDateTime(instance.lastDecisionAt))}</p>
      ${renderCooldownNotice(instance.exchangeCooldown, "instance-cooldown")}
      ${(instance.warnings || []).length ? `<p class="instance-warning">${escapeHtml(instance.warnings.join("；"))}</p>` : ""}
      <div class="instance-card-actions">
        <button type="button" data-instance-view="${escapeHtml(instance.id)}">查看</button>
        <button type="button" class="secondary-button" data-instance-toggle="${escapeHtml(instance.id)}">${instance.running ? "暂停" : "启动"}</button>
        <button type="button" class="secondary-button" data-instance-rename="${escapeHtml(instance.id)}">重命名</button>
        <button type="button" class="secondary-button danger-outline" data-instance-delete="${escapeHtml(instance.id)}">删除</button>
      </div>
    </article>
  `).join("");
  if (!cards.length) {
    els.instanceGrid.innerHTML = `<p class="empty">当前筛选条件下还没有实例。</p>`;
  }
}

function evolutionRunnerState(runner) {
  if (runner?.running) return { label: "Cycle Running", className: "is-running" };
  if (runner?.lastError) return { label: "Cycle Error", className: "is-error" };
  if (runner?.lastFinishedAt) return { label: "Cycle Ready", className: "is-ready" };
  return { label: "Cycle Idle", className: "is-idle" };
}

function describeEvolutionResult(runner) {
  const result = runner?.lastResult;
  if (!result) {
    if (runner?.lastError) return "最近一轮已失败";
    return runner?.lastFinishedAt ? "最近一轮未生成摘要" : "尚未执行过 cycle";
  }
  const pieces = [];
  if (Number.isFinite(Number(result.familyScore))) pieces.push(`family ${fmtScore(result.familyScore)}`);
  if (result.insufficientSample) pieces.push("样本不足");
  if (result.candidatePresetId) pieces.push(`candidate ${result.candidatePresetId}`);
  if (result.promotionInstanceId) pieces.push(`promote ${result.promotionInstanceId}`);
  return pieces.join(" · ") || "最近一轮已完成";
}

function describeEvolutionRunnerMeta(runner) {
  const pieces = [];
  if (runner?.lastReason) pieces.push(`reason ${runner.lastReason}`);
  if (runner?.lastStartedAt) pieces.push(`start ${fmtDateTime(runner.lastStartedAt)}`);
  if (runner?.lastFinishedAt) pieces.push(`finish ${fmtDateTime(runner.lastFinishedAt)}`);
  if (Number.isFinite(Number(runner?.lastDurationSeconds))) pieces.push(`耗时 ${fmtOptionalDuration(runner.lastDurationSeconds)}`);
  return pieces.join(" · ") || "尚无运行记录";
}

function renderEvolution() {
  const families = state.evolution?.families || [];
  const promotableCount = families.filter((item) => item?.promotionPreview?.promotable).length;
  const runningCount = families.filter((item) => item?.evolutionRunner?.running).length;
  const errorCount = families.filter((item) => item?.evolutionRunner?.lastError).length;
  els.evolutionMeta.textContent = families.length
    ? `共 ${families.length} 条 family，运行中 ${runningCount} 条，可晋升 ${promotableCount} 条，异常 ${errorCount} 条`
    : "还没有 strategy family，可先从某个 paper instance 建一条演化线。";

  els.familyGrid.innerHTML = families.map((family) => {
    const preview = family.promotionPreview;
    const active = family.activeInstance;
    const latestCandidate = family.latestCandidate;
    const lastPromotion = family.lastPromotion;
    const activeReview = family.latestActiveReview;
    const familyReview = family.latestFamilyReview;
    const shadows = family.shadowInstances || [];
    const runner = family.evolutionRunner || {};
    const runnerState = evolutionRunnerState(runner);
    const isBusy = Boolean(runner.running);
    const promotableShadowId = preview?.promotable ? preview.shadowInstanceId : "";
    return `
      <article class="instance-card family-card">
        <div class="instance-card-top">
          <div>
            <p class="instance-type">FAMILY</p>
            <h2>${escapeHtml(family.name)}</h2>
            <p class="meta">${escapeHtml(family.id)} · Active ${escapeHtml(active?.name || family.activeInstanceId || "n/a")}</p>
          </div>
          <div class="family-badge-row">
            <div class="family-badge ${preview?.promotable ? "is-promotable" : "is-idle"}">
              ${escapeHtml(preview?.promotable ? "可晋升" : "观察中")}
            </div>
            <div class="family-badge ${runnerState.className}">
              ${escapeHtml(runnerState.label)}
            </div>
          </div>
        </div>
        <div class="instance-stats-grid family-stats-grid">
          <span>Family Review <strong>${escapeHtml(fmtScore(familyReview?.finalScore))}</strong></span>
          <span>Active Review <strong>${escapeHtml(fmtScore(activeReview?.finalScore))}</strong></span>
          <span>Shadow 数量 <strong>${escapeHtml(String(shadows.length))}</strong></span>
          <span>Promotion 次数 <strong>${escapeHtml(String(family.promotionCount || 0))}</strong></span>
        </div>
        <div class="family-panel">
          <div>
            <p class="family-label">最近 Candidate</p>
            <strong>${escapeHtml(latestCandidate?.name || "暂无")}</strong>
            <p class="meta">${escapeHtml(latestCandidate?.presetId || "还未生成候选策略")}</p>
          </div>
          <div>
            <p class="family-label">晋升预览</p>
            <strong>${escapeHtml(preview ? `${fmtScore(preview.shadowScore)} vs ${fmtScore(preview.activeScore)}` : "暂无可比较结果")}</strong>
            <p class="meta">${escapeHtml(preview ? `delta ${fmtScore(preview.scoreDelta)} / threshold ${fmtScore(preview.requiredScoreDelta)}` : "先跑 active/shadow review" )}</p>
          </div>
        </div>
        <div class="family-panel">
          <div>
            <p class="family-label">最近 Cycle</p>
            <strong>${escapeHtml(describeEvolutionResult(runner))}</strong>
            <p class="meta">${escapeHtml(describeEvolutionRunnerMeta(runner))}</p>
          </div>
          <div>
            <p class="family-label">Runner Error</p>
            <strong>${escapeHtml(runner.lastError || "none")}</strong>
            <p class="meta">${escapeHtml(runner.lastError ? "需要排查最近一轮的异常链路" : "最近一轮没有异常")}</p>
          </div>
        </div>
        <div class="family-shadow-list">
          ${shadows.length
            ? shadows.map((shadow) => `
              <article class="family-shadow-item">
                <div class="family-shadow-copy">
                  <strong>${escapeHtml(shadow.name)}</strong>
                  <span>${escapeHtml(shadow.id)}</span>
                </div>
                <div class="family-shadow-actions">
                  <button type="button" class="secondary-button" data-shadow-view="${escapeHtml(shadow.id)}">查看</button>
                  <button type="button" class="secondary-button danger-outline" data-shadow-retire="${escapeHtml(shadow.id)}" data-family-id="${escapeHtml(family.id)}">Retire</button>
                </div>
              </article>
            `).join("")
            : `<p class="empty">暂无 shadow instance。</p>`}
        </div>
        <p class="meta">最近晋升 ${escapeHtml(lastPromotion ? `${fmtDateTime(lastPromotion.approvedAt)} · ${lastPromotion.toInstanceId}` : "暂无")}</p>
        <div class="instance-card-actions">
          <button type="button" data-family-cycle="${escapeHtml(family.id)}" ${isBusy ? "disabled" : ""}>${escapeHtml(isBusy ? "Cycle Running" : "Run Cycle")}</button>
          <button type="button" class="secondary-button" data-family-review="${escapeHtml(family.id)}" ${isBusy ? "disabled" : ""}>Run Review</button>
          <button type="button" class="secondary-button" data-family-candidate="${escapeHtml(family.id)}" ${isBusy ? "disabled" : ""}>Create Candidate</button>
          <button
            type="button"
            class="secondary-button"
            data-family-promote="${escapeHtml(family.id)}"
            data-family-shadow="${escapeHtml(promotableShadowId)}"
            ${promotableShadowId && !isBusy ? "" : "disabled"}
          >Promote</button>
        </div>
      </article>
    `;
  }).join("");

  if (!families.length) {
    els.familyGrid.innerHTML = `<p class="empty">当前还没有 evolution family。</p>`;
  }
}

async function loadWorkbench() {
  const [payload, evolution] = await Promise.all([
    getJson("/api/instances"),
    getJson("/api/evolution/families")
  ]);
  state.payload = payload;
  state.evolution = evolution;
  renderWorkbench();
  renderEvolution();
}

async function handleCreate(type) {
  const defaultName = type === "live" ? "New Live" : "New Paper";
  const name = window.prompt("请输入实例名称", defaultName);
  if (!name) return;
  await postJson("/api/instances", { name, type });
  await loadWorkbench();
}

async function handleCreateFamily() {
  const paperInstances = (state.payload?.instances || []).filter((item) => item.type === "paper");
  if (!paperInstances.length) {
    window.alert("请先创建至少一个 paper instance。");
    return;
  }
  const defaultActiveId = paperInstances[0].id;
  const activeInstanceId = window.prompt(
    `请输入 active paper instance id。\n可选：${paperInstances.map((item) => `${item.id}(${item.name})`).join("，")}`,
    defaultActiveId
  );
  if (!activeInstanceId) return;
  const name = window.prompt("请输入 family 名称", `${paperInstances.find((item) => item.id === activeInstanceId)?.name || activeInstanceId} Evolution Line`);
  if (!name) return;
  await postJson("/api/evolution/families", { activeInstanceId, name });
  await loadWorkbench();
}

async function handleToggle(instanceId) {
  const instance = (state.payload?.instances || []).find((item) => item.id === instanceId);
  if (!instance) return;
  const nextEnabled = !instance.running;
  const payload = instance.type === "live"
    ? { liveTrading: { enabled: nextEnabled } }
    : { paperTrading: { enabled: nextEnabled } };
  await postJson(`/api/instances/${encodeURIComponent(instanceId)}/trading/settings`, payload);
  await loadWorkbench();
}

async function handleRename(instanceId) {
  const instance = (state.payload?.instances || []).find((item) => item.id === instanceId);
  if (!instance) return;
  const name = window.prompt("请输入新的实例名称", instance.name);
  if (!name) return;
  await postJson(`/api/instances/${encodeURIComponent(instanceId)}/rename`, { name });
  await loadWorkbench();
}

async function handleDelete(instanceId) {
  const instance = (state.payload?.instances || []).find((item) => item.id === instanceId);
  if (!instance) return;
  if (!window.confirm(`确认删除实例「${instance.name}」？这只会删除本地实例数据。`)) return;
  await postJson(`/api/instances/${encodeURIComponent(instanceId)}/delete`, {});
  await loadWorkbench();
}

async function handleRunReview(familyId) {
  const payload = await postJson("/api/evolution/review/run", { familyId });
  const familyReview = payload.familyReview;
  const preview = payload.promotionPreview;
  window.alert(
    `Review 完成\nfamily score: ${fmtScore(familyReview?.finalScore)}\n` +
    `promotable: ${preview?.promotable ? "yes" : "no"}\n` +
    `delta: ${fmtScore(preview?.scoreDelta)}`
  );
  await loadWorkbench();
}

async function handleRunCycle(familyId) {
  const payload = await postJson("/api/evolution/cycle/start", { familyId, reason: "manual_cycle" });
  if (!payload.started) {
    window.alert("上一轮 evolution cycle 仍在执行，请稍后再试。");
  }
  await loadWorkbench();
}

async function handleCreateCandidate(familyId) {
  const payload = await postJson("/api/evolution/candidate/create", { familyId, createShadow: true });
  const preset = payload.candidate?.preset;
  const shadow = payload.shadow?.instance;
  window.alert(
    `Candidate 已生成\npreset: ${preset?.id || "n/a"}\n` +
    `shadow: ${shadow?.id || "未创建"}`
  );
  await loadWorkbench();
}

async function handlePromote(familyId, preferredShadowId = "") {
  const family = (state.evolution?.families || []).find((item) => item.id === familyId);
  if (!family) return;
  const shadowIds = (family.shadowInstances || []).map((item) => item.id);
  const shadowInstanceId = preferredShadowId || shadowIds[0] || window.prompt(
    `请输入要晋升的 shadow instance id。\n可选：${shadowIds.join("，")}`,
    shadowIds[0] || ""
  );
  if (!shadowInstanceId) return;
  const preview = family.promotionPreview;
  const reason = window.prompt("请输入 promotion 原因", "manual_workbench_promote");
  if (!reason) return;
  if (!window.confirm(`确认将 ${shadowInstanceId} 晋升为 ${familyId} 的 active instance？`)) return;
  await postJson("/api/evolution/promote", {
    familyId,
    shadowInstanceId,
    reason,
    scoreDelta: preview?.shadowInstanceId === shadowInstanceId ? preview?.scoreDelta : undefined,
    auto: false
  });
  await loadWorkbench();
}

async function handleRetireShadow(familyId, shadowInstanceId) {
  const family = (state.evolution?.families || []).find((item) => item.id === familyId);
  const shadow = (family?.shadowInstances || []).find((item) => item.id === shadowInstanceId);
  const shadowName = shadow?.name || shadowInstanceId;
  if (!window.confirm(`确认退役 shadow「${shadowName}」？\n这会将它从 family 中移除，并删除本地实例数据。`)) return;
  await postJson(`/api/instances/${encodeURIComponent(shadowInstanceId)}/retire-shadow`, {
    reason: "manual_workbench_shadow_retire"
  });
  await loadWorkbench();
}

els.createPaperBtn?.addEventListener("click", () => handleCreate("paper"));
els.createLiveBtn?.addEventListener("click", () => handleCreate("live"));
els.createFamilyBtn?.addEventListener("click", () => void handleCreateFamily());
els.refreshWorkbenchBtn?.addEventListener("click", () => void loadWorkbench());
els.workbenchSummary?.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const button = target.closest("[data-filter-id]");
  if (!(button instanceof HTMLElement)) return;
  state.filter = button.dataset.filterId || "all";
  renderWorkbench();
});
els.instanceGrid?.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const viewId = target.dataset.instanceView;
  if (viewId) {
    window.location.href = `/trader.html?instance=${encodeURIComponent(viewId)}`;
    return;
  }
  const toggleId = target.dataset.instanceToggle;
  if (toggleId) {
    void handleToggle(toggleId);
    return;
  }
  const renameId = target.dataset.instanceRename;
  if (renameId) {
    void handleRename(renameId);
    return;
  }
  const deleteId = target.dataset.instanceDelete;
  if (deleteId) {
    void handleDelete(deleteId);
  }
});
els.familyGrid?.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const shadowViewId = target.dataset.shadowView;
  if (shadowViewId) {
    window.location.href = `/trader.html?instance=${encodeURIComponent(shadowViewId)}`;
    return;
  }
  const shadowRetireId = target.dataset.shadowRetire;
  if (shadowRetireId) {
    void handleRetireShadow(target.dataset.familyId || "", shadowRetireId);
    return;
  }
  const cycleFamilyId = target.dataset.familyCycle;
  if (cycleFamilyId) {
    void handleRunCycle(cycleFamilyId);
    return;
  }
  const reviewFamilyId = target.dataset.familyReview;
  if (reviewFamilyId) {
    void handleRunReview(reviewFamilyId);
    return;
  }
  const candidateFamilyId = target.dataset.familyCandidate;
  if (candidateFamilyId) {
    void handleCreateCandidate(candidateFamilyId);
    return;
  }
  const promoteFamilyId = target.dataset.familyPromote;
  if (promoteFamilyId) {
    void handlePromote(promoteFamilyId, target.dataset.familyShadow || "");
  }
});

applyTheme();
void loadWorkbench().catch((error) => {
  els.workbenchMeta.textContent = `加载失败：${error.message}`;
  if (els.evolutionMeta) {
    els.evolutionMeta.textContent = `加载失败：${error.message}`;
  }
});
