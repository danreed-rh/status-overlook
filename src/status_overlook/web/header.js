(() => {
  const button = document.getElementById("btnRun");
  const statusLine = document.getElementById("runStatus");
  const MAX_WAIT_MS = 5 * 60 * 1000;
  let running = false;
  let messageVersion = 0;

  function showMessage(message, error = false) {
    const version = ++messageVersion;
    statusLine.hidden = !message;
    statusLine.textContent = message || "";
    statusLine.classList.toggle("refresh-error", error);
    if (message === "Refresh finished.") {
      setTimeout(() => {
        if (version === messageVersion && !running) showMessage("");
      }, 2500);
    }
  }

  function elapsedLabel(startedAt) {
    if (!startedAt) return "";
    const time = Date.parse(startedAt.endsWith("Z") ? startedAt : `${startedAt}Z`);
    if (Number.isNaN(time)) return "";
    return ` (${Math.max(0, Math.round((Date.now() - time) / 1000))}s)`;
  }

  async function waitForRun() {
    const start = Date.now();
    while (Date.now() - start < MAX_WAIT_MS) {
      const response = await fetch("/api/status");
      if (!response.ok) throw new Error(`status ${response.status}`);
      const status = await response.json();
      if (!status.running) {
        if (status.last_error) showMessage(`Last refresh failed: ${status.last_error}`, true);
        else if (status.last_ok === true) showMessage("Refresh finished.");
        else showMessage(`Last refresh exited with code ${status.last_code}`, true);
        window.dispatchEvent(new CustomEvent("status-overlook:refresh-complete", { detail: status }));
        return;
      }
      showMessage(
        `Refreshing store and digests (calls gh/acli)…${elapsedLabel(status.started_at)}` +
          (status.phase ? ` — ${status.phase}` : "")
      );
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    showMessage("Refresh is still running — check the serve terminal or try again later.");
  }

  async function refresh(force = true) {
    if (running) return;
    running = true;
    button.disabled = true;
    showMessage("Starting refresh…");
    window.dispatchEvent(new CustomEvent("status-overlook:refresh-start"));
    try {
      const response = await fetch("/api/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: Boolean(force) }),
      });
      if (response.status === 202 || response.status === 409) {
        await waitForRun();
        return;
      }
      if (response.status === 200) {
        const data = await response.json().catch(() => ({}));
        if (data.skipped === "working_hours") {
          showMessage("Skipped — outside working hours. Click Refresh now to sync anyway.");
          return;
        }
      }
      showMessage(`Could not start refresh (${response.status})`, true);
    } catch (error) {
      showMessage(`Lost connection while refreshing: ${error}`, true);
    } finally {
      button.disabled = false;
      running = false;
    }
  }

  async function resumeActiveRun() {
    try {
      const response = await fetch("/api/status");
      if (!response.ok || running) return;
      const status = await response.json();
      if (!status.running || running) return;
      running = true;
      button.disabled = true;
      window.dispatchEvent(new CustomEvent("status-overlook:refresh-start"));
      try {
        await waitForRun();
      } catch (error) {
        showMessage(`Lost connection while refreshing: ${error}`, true);
      } finally {
        button.disabled = false;
        running = false;
      }
    } catch {
      // The page can still render cached data while the local server is offline.
    }
  }

  button.addEventListener("click", () => refresh(true));
  window.StatusOverlookHeader = { refresh, isRunning: () => running, showMessage };
  document.addEventListener("DOMContentLoaded", resumeActiveRun, { once: true });
})();
