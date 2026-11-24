(() => {
  const $ = (id) => document.getElementById(id);
  const main = $("main");
  const meta = $("meta");
  const btnMark = $("btnMark");

  let autoTimer = null;
  const PREFS_KEY = "status-overlook.ui";
  const CONTROL_IDS = ["view", "source", "sinceRead", "interval"];

  function qs() {
    const params = new URLSearchParams({
      view: $("view").value,
      source: $("source").value,
      since_read: $("sinceRead").checked ? "1" : "0",
    });
    return params.toString();
  }

  function readStoredPrefs() {
    try {
      return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}") || {};
    } catch {
      return {};
    }
  }

  function currentPrefs() {
    return {
      view: $("view").value,
      source: $("source").value,
      since_read: $("sinceRead").checked ? "1" : "0",
      interval: $("interval").value,
    };
  }

  function persistPrefs() {
    const prefs = currentPrefs();
    try {
      localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
    } catch {
      /* ignore quota / private mode */
    }
    const url = new URL(window.location.href);
    url.searchParams.set("view", prefs.view);
    url.searchParams.set("source", prefs.source);
    url.searchParams.set("since_read", prefs.since_read);
    url.searchParams.set("interval", prefs.interval);
    history.replaceState(null, "", url.pathname + url.search + url.hash);
  }

  function setSelectValue(el, value) {
    if (value == null || value === "") return;
    const ok = Array.from(el.options).some((o) => o.value === String(value));
    if (ok) el.value = String(value);
  }

  function restorePrefs() {
    const url = new URLSearchParams(window.location.search);
    const stored = readStoredPrefs();
    const view = url.get("view") || stored.view;
    const source = url.get("source") || stored.source;
    const since =
      url.get("since_read") ??
      url.get("sinceRead") ??
      stored.since_read;
    const interval = url.get("interval") || stored.interval;

    setSelectValue($("view"), view);
    setSelectValue($("source"), source);
    setSelectValue($("interval"), interval);
    if (since === "1" || since === "true") $("sinceRead").checked = true;
    else if (since === "0" || since === "false") $("sinceRead").checked = false;

    persistPrefs();
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  const CUE_PILL_CLS = {
    actionable: "pill-actionable",
    pending: "pill-pending",
    blocked: "pill-blocked",
    done: "pill-done",
  };

  function cuePill(cue) {
    if (!cue || !cue.label) return "";
    const kind = String(cue.kind || "").toLowerCase();
    const cls = CUE_PILL_CLS[kind] || "";
    return `<span class="pill ${cls}" title="${esc(cue.label)}">${esc(cue.label)}</span>`;
  }

  function statusAgeLabel(changedAt) {
    if (!changedAt) return "";
    const changed = Date.parse(changedAt);
    if (Number.isNaN(changed)) return "";
    const seconds = Math.max(0, Math.floor((Date.now() - changed) / 1000));
    if (seconds < 86400) return "<1d";
    return `${Math.floor(seconds / 86400)}d`;
  }

  function statusAgeMarkup(changedAt, source) {
    if (!changedAt) return "";
    return `<span class="status-age" data-state-changed-at="${esc(changedAt)}" data-source="${esc(source)}"></span>`;
  }

  function updateStatusAges() {
    document.querySelectorAll(".status-age").forEach((el) => {
      const age = statusAgeLabel(el.dataset.stateChangedAt);
      el.textContent = age;
      if (age) el.title = `Time in ${el.dataset.source === "github_pr" ? "PR's " : ""}current status: ${age}`;
    });
  }

  function statusMarkup(item) {
    return `<div class="item-state">
      <span class="status">${esc(item.display_status || item.remote_status || "—")}</span>
      ${statusAgeMarkup(item.state_changed_at, item.source)}
    </div>`;
  }

  function renderGroup(g) {
    const p = g.primary;
    const href = p.url ? `href="${esc(p.url)}" target="_blank" rel="noopener"` : "";
    const linkedKeys = (g.linked || [])
      .map((m) => {
        const lh = m.url ? `href="${esc(m.url)}" target="_blank" rel="noopener"` : "";
        return `<a class="linked" ${lh}>↔ ${esc(m.short_key)}</a>`;
      })
      .join(" ");
    const statusItem = [p, ...(g.linked || [])].find((m) => m.id === g.status_item_id) || p;
    const cue = g.cue || p.cue;
    return `
      <article class="item">
        <div class="item-head">
          <div class="item-identity">
            ${g.unread ? '<span class="badge unread">● unread</span>' : ""}
            <a class="key" ${href}>${esc(p.short_key)}</a>
            ${linkedKeys}
            ${cuePill(cue)}
            ${p.epic ? '<span class="badge epic">[Epic]</span>' : ""}
          </div>
          ${statusMarkup(statusItem)}
        </div>
        <p class="summary">${esc(p.summary || "—")}</p>
      </article>`;
  }

  function sectionWeight(sec) {
    return sec.count ?? (sec.groups ? sec.groups.length : 0);
  }

  function partitionSections(sections) {
    const left = [];
    const right = [];
    let leftWeight = 0;
    let rightWeight = 0;

    const actionable = sections.find((s) => s.id === "actionable");
    const rest = sections.filter((s) => s.id !== "actionable");

    if (actionable) {
      left.push(actionable);
      leftWeight = sectionWeight(actionable);
    }

    for (const sec of rest) {
      const w = sectionWeight(sec);
      if (leftWeight <= rightWeight) {
        left.push(sec);
        leftWeight += w;
      } else {
        right.push(sec);
        rightWeight += w;
      }
    }

    return { left, right };
  }

  function renderSection(sec) {
    const body =
      sec.groups && sec.groups.length
        ? sec.groups.map(renderGroup).join("")
        : '<p class="empty">None</p>';
    return `
      <section class="section" data-section="${esc(sec.id)}">
        <h2>${esc(sec.title)} <span class="count">(${sec.count})</span></h2>
        ${body}
      </section>`;
  }

  function render(data) {
    meta.textContent = `Store ${data.store_updated_at || "—"} · shown ${data.generated_at || ""}`;
    if (!data.sections || !data.sections.length) {
      main.classList.remove("layout-multi");
      main.innerHTML = '<p class="empty">No sections</p>';
      return;
    }
    if (data.sections.length > 1) {
      main.classList.add("layout-multi");
      const { left, right } = partitionSections(data.sections);
      main.innerHTML = `
        <div class="layout-col layout-col-left">${left.map(renderSection).join("")}</div>
        <div class="layout-col layout-col-right">${right.map(renderSection).join("")}</div>`;
      updateStatusAges();
      return;
    }
    main.classList.remove("layout-multi");
    main.innerHTML = renderSection(data.sections[0]);
    updateStatusAges();
  }

  async function loadDigest() {
    const res = await fetch("/api/digest?" + qs());
    if (!res.ok) throw new Error("digest " + res.status);
    render(await res.json());
  }

  async function markRead() {
    btnMark.disabled = true;
    try {
      const res = await fetch("/api/mark-read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ all: true }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || res.status);
      await loadDigest();
    } catch (e) {
      window.StatusOverlookHeader.showMessage(String(e), true);
    } finally {
      btnMark.disabled = false;
    }
  }

  function setupAuto() {
    clearInterval(autoTimer);
    autoTimer = null;
    const sec = Number($("interval").value || 0);
    if (sec > 0) {
      autoTimer = setInterval(() => {
        if (!window.StatusOverlookHeader.isRunning()) window.StatusOverlookHeader.refresh(false);
      }, sec * 1000);
    }
  }

  function onControlsChange() {
    persistPrefs();
    loadDigest().catch(console.error);
    setupAuto();
  }

  CONTROL_IDS.forEach((id) => {
    $(id).addEventListener("change", onControlsChange);
  });
  btnMark.addEventListener("click", () => markRead());
  window.addEventListener("status-overlook:refresh-complete", () => {
    loadDigest().catch((error) => window.StatusOverlookHeader.showMessage(String(error), true));
  });

  restorePrefs();
  const originEl = $("uiOrigin");
  if (originEl) {
    originEl.textContent = window.location.origin + "/";
  }
  loadDigest().catch((e) => {
    meta.textContent = String(e);
  });
  setupAuto();
  setInterval(updateStatusAges, 60 * 1000);
})();
