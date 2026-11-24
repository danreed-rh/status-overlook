(() => {
  const $ = (id) => document.getElementById(id);
  let lastSnapshot = "";
  let lastTeamUpdatedAt = "";
  let refreshStartedTeamAt = "";

  function esc(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function ageDays(enteredAt) {
    const time = Date.parse(enteredAt || "");
    if (!Number.isFinite(time)) return "";
    const days = Math.max(0, Math.floor((Date.now() - time) / 86400000));
    return days ? `${days}d` : "<1d";
  }

  function showStatus(message, error = false) {
    $("teamStatus").hidden = !message;
    $("teamStatus").textContent = message;
    $("teamStatus").classList.toggle("team-error", error);
  }

  function renderMembers(members) {
    $("memberCount").textContent = `(${members.length})`;
    $("memberList").innerHTML = members.length
      ? members.map((login) => `<li><a href="https://github.com/${esc(login)}" target="_blank" rel="noopener">@${esc(login)}</a><button type="button" class="member-remove" data-login="${esc(login)}" aria-label="Remove ${esc(login)}">Remove</button></li>`).join("")
      : '<li class="team-empty">No team members yet. Add a GitHub username to start.</li>';
  }

  function renderCard(pr) {
    const number = Number(pr.number);
    const href = `https://github.com/${encodeURI(pr.repo)}/pull/${number}`;
    const author = esc(pr.author);
    const age = ageDays(pr.entered_at);
    return `<article class="team-card">
      <div class="team-card-head">
        <a class="team-pr-key" href="${esc(href)}" target="_blank" rel="noopener">${esc(pr.repo)}#${number}</a>
        ${age ? `<span class="team-age" data-entered-at="${esc(pr.entered_at)}" title="Observed time in this queue">${age}</span>` : ""}
      </div>
      <a class="team-pr-title" href="${esc(href)}" target="_blank" rel="noopener">${esc(pr.title)}</a>
      <div class="team-card-foot">
        <a class="team-author" href="https://github.com/${author}" target="_blank" rel="noopener">@${author}</a>
        <span class="team-signal">Review required</span>
        ${pr.queue === "lgtm" && pr.unassigned ? '<span class="team-signal">Unassigned</span>' : ""}
      </div>
    </article>`;
  }

  function renderSection(title, description, queue, items) {
    const content = items.length
      ? items.map(renderCard).join("")
      : '<p class="team-empty">Nothing needs attention here right now.</p>';
    return `<section class="team-section team-section-${queue}">
      <div class="team-section-head"><h3>${title} <span>(${items.length})</span></h3><p>${description}</p></div>
      <div class="team-section-body">${content}</div>
    </section>`;
  }

  function render(data) {
    const members = data.members || [];
    renderMembers(members);
    const items = data.items || [];
    const unassigned = items.filter((item) => item.queue === "unassigned").sort((a, b) => a.entered_at.localeCompare(b.entered_at));
    const lgtm = items.filter((item) => item.queue === "lgtm").sort((a, b) => a.entered_at.localeCompare(b.entered_at));
    $("teamCounts").textContent = `${unassigned.length} unassigned · ${lgtm.length} LGTM`;
    $("teamUpdated").textContent = data.updated_at ? `Last checked ${new Date(data.updated_at).toLocaleString()}` : "Not refreshed yet";
    $("teamMeta").textContent = `${members.length} tracked teammates · ${data.updated_at ? "cached results" : "no results yet"}`;
    $("teamSections").innerHTML = members.length
      ? renderSection("Unassigned", "Review required · no GitHub assignee · any visible repository", "unassigned", unassigned)
        + renderSection("LGTM · required review", "You have Maintain/Admin access to the repository", "lgtm", lgtm)
      : '<p class="team-empty team-setup">No team members configured. Add GitHub usernames above, then refresh.</p>';
    showStatus(data.last_error ? `Team results may be stale: ${data.last_error}` : "", Boolean(data.last_error));
  }

  async function loadTeam() {
    const response = await fetch("/api/team");
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Could not load team queue (${response.status})`);
    lastTeamUpdatedAt = data.updated_at || "";
    const snapshot = JSON.stringify(data);
    if (snapshot !== lastSnapshot) {
      render(data);
      lastSnapshot = snapshot;
    } else {
      document.querySelectorAll(".team-age").forEach((el) => {
        el.textContent = ageDays(el.dataset.enteredAt);
      });
    }
    return data;
  }

  async function changeMember(action, login) {
    const response = await fetch("/api/team/members", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, login }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `Member update failed (${response.status})`);
    await loadTeam();
  }

  $("memberForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = $("memberLogin");
    try {
      const login = input.value.trim();
      await changeMember("add", login);
      input.value = "";
      showStatus(`Tracking @${login}. Refresh now to load their PRs.`);
    } catch (error) {
      showStatus(String(error), true);
    }
  });
  $("memberList").addEventListener("click", async (event) => {
    const button = event.target.closest(".member-remove");
    if (!button) return;
    button.disabled = true;
    try {
      const login = button.dataset.login;
      await changeMember("remove", login);
      showStatus(`Removed @${login} from the team queue.`);
    } catch (error) {
      showStatus(String(error), true);
      button.disabled = false;
    }
  });
  window.addEventListener("status-overlook:refresh-start", () => {
    refreshStartedTeamAt = lastTeamUpdatedAt;
    showStatus("");
  });
  window.addEventListener("status-overlook:refresh-complete", async () => {
    try {
      const team = await loadTeam();
      if (team.last_error) return;
      if (team.updated_at && team.updated_at !== refreshStartedTeamAt) {
        showStatus("Team queue updated.");
      }
    } catch (error) {
      showStatus(String(error), true);
    }
  });
  loadTeam().catch((error) => showStatus(String(error), true));
  setInterval(() => {
    if (!window.StatusOverlookHeader.isRunning()) loadTeam().catch((error) => showStatus(String(error), true));
  }, 60000);
})();
