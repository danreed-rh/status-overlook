(() => {
  const $ = (id) => document.getElementById(id);
  const main = $("main");
  const meta = $("meta");
  const runStatus = $("runStatus");
  const btnRun = $("btnRun");
  const btnMark = $("btnMark");

  let autoTimer = null;
  let pollTimer = null;
  let waitStarted = 0;
  const MAX_WAIT_MS = 5 * 60 * 1000;
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

  function renderGroup(g) {
    const p = g.primary;
    const href = p.url ? `href="${esc(p.url)}" target="_blank" rel="noopener"` : "";
    const linked = (g.linked || [])
      .map((m) => {
        const lh = m.url ? `href="${esc(m.url)}" target="_blank" rel="noopener"` : "";
        return `<a class="linked" ${lh}>↔ ${esc(m.short_key)}</a>`;
      })
      .join(" ");
    const cue = g.cue || p.cue;
    return `
      <article class="item">
        <div class="item-head">
          ${g.unread ? '<span class="badge unread">● unread</span>' : ""}
          <a class="key" ${href}>${esc(p.short_key)}</a>
          ${cuePill(cue)}
          ${p.epic ? '<span class="badge epic">[Epic]</span>' : ""}
          ${linked}
          <span class="status">${esc(p.remote_status || "—")}</span>
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
      return;
    }
    main.classList.remove("layout-multi");
    main.innerHTML = renderSection(data.sections[0]);
  }

  async function loadDigest() {
    const res = await fetch("/api/digest?" + qs());
    if (!res.ok) throw new Error("digest " + res.status);
    render(await res.json());
  }

  function elapsedLabel(startedAt) {
    if (!startedAt) return "";
    const t = Date.parse(startedAt.endsWith("Z") ? startedAt : startedAt + "Z");
    if (Number.isNaN(t)) return "";
    const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
    return ` (${sec}s)`;
  }

  async function pollRun() {
    const res = await fetch("/api/status");
    if (!res.ok) throw new Error("status " + res.status);
    const st = await res.json();
    if (st.running) {
      runStatus.hidden = false;
      const phase = st.phase ? ` — ${st.phase}` : "";
      runStatus.textContent =
        "Refreshing store and digests (calls gh/acli; often 15–40s)…" +
        elapsedLabel(st.started_at) +
        phase;
      btnRun.disabled = true;
      return true;
    }
    btnRun.disabled = false;
    if (st.last_error) {
      runStatus.hidden = false;
      const tail = st.log_tail ? " · " + String(st.log_tail).trim().split("\n").slice(-1)[0] : "";
      runStatus.textContent = "Last refresh failed: " + st.last_error + tail;
    } else if (st.last_ok === false) {
      runStatus.hidden = false;
      runStatus.textContent = "Last refresh exited with code " + st.last_code;
    } else if (st.last_ok === true) {
      runStatus.hidden = false;
      runStatus.textContent = "Refresh finished.";
      setTimeout(() => {
        if (!btnRun.disabled) {
          runStatus.hidden = true;
          runStatus.textContent = "";
        }
      }, 2500);
    } else {
      runStatus.hidden = true;
      runStatus.textContent = "";
    }
    return false;
  }

  function stopWait(message) {
    clearInterval(pollTimer);
    pollTimer = null;
    btnRun.disabled = false;
    if (message) {
      runStatus.hidden = false;
      runStatus.textContent = message;
    }
  }

  async function waitForRun() {
    clearInterval(pollTimer);
    waitStarted = Date.now();
    const tick = async () => {
      try {
        if (Date.now() - waitStarted > MAX_WAIT_MS) {
          stopWait(
            "Refresh still running after 5 minutes — check the serve terminal. You can click Refresh again later."
          );
          return;
        }
        const running = await pollRun();
        if (!running) {
          clearInterval(pollTimer);
          pollTimer = null;
          try {
            await loadDigest();
          } catch (e) {
            runStatus.hidden = false;
            runStatus.textContent = String(e);
          }
        }
      } catch (e) {
        stopWait("Lost connection while refreshing: " + e);
      }
    };
    pollTimer = setInterval(tick, 500);
    await tick();
  }

  async function startRun() {
    btnRun.disabled = true;
    runStatus.hidden = false;
    runStatus.textContent = "Starting refresh…";
    try {
      const res = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      if (res.status === 409) {
        await waitForRun();
        return;
      }
      if (!res.ok) {
        runStatus.textContent = "Could not start refresh (" + res.status + ")";
        btnRun.disabled = false;
        return;
      }
      await waitForRun();
    } catch (e) {
      stopWait("Could not start refresh: " + e);
    }
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
      runStatus.hidden = false;
      runStatus.textContent = String(e);
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
        if (!btnRun.disabled) startRun();
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
  btnRun.addEventListener("click", () => startRun());
  btnMark.addEventListener("click", () => markRead());

  restorePrefs();
  loadDigest().catch((e) => {
    meta.textContent = String(e);
  });
  setupAuto();
})();
