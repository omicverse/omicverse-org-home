// ─── Mobile nav toggle ─────────────────────────────
const navToggle = document.querySelector(".nav-toggle");
const navLinks = document.querySelector(".nav-links");

if (navToggle && navLinks) {
  navToggle.addEventListener("click", () => {
    const expanded = navToggle.getAttribute("aria-expanded") === "true";
    navToggle.setAttribute("aria-expanded", String(!expanded));
    navLinks.classList.toggle("open", !expanded);
  });
}

// ─── Filter binding (rebound after dynamic render) ──
function bindPackageFilter() {
  const filterButtons = document.querySelectorAll("[data-filter]");
  const filterTargets = document.querySelectorAll("[data-tags]");
  filterButtons.forEach((button) => {
    if (button._bound) return;
    button._bound = true;
    button.addEventListener("click", () => {
      const filter = button.dataset.filter || "all";
      filterButtons.forEach((item) => item.classList.toggle("active", item === button));
      filterTargets.forEach((card) => {
        const tags = card.getAttribute("data-tags") || "";
        const visible = filter === "all" || tags.split(/\s+/).includes(filter);
        card.classList.toggle("is-hidden", !visible);
      });
    });
  });
}
bindPackageFilter();

// ─── Tiny utilities ────────────────────────────────
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[c]);
}

function repoLogoUrl(repo) {
  return `https://raw.githubusercontent.com/${repo.full_name}/${repo.default_branch || "main"}/logo/logo.svg`;
}

function bindRepoLogoErrors(root = document) {
  root.querySelectorAll("img[data-repo-logo]").forEach((img) => {
    if (img._repoLogoErrorBound) return;
    img._repoLogoErrorBound = true;
    img.addEventListener("error", () => {
      const logoLink = img.closest(".package-logo-link");
      if (logoLink) {
        logoLink.remove();
        return;
      }
      const holder = img.closest(".t-logo");
      if (holder) holder.classList.add("is-missing-logo");
    });
  });
}

// ─── GitHub API: contributors (cached per session) ──
async function fetchContributors(repo) {
  const key = `gh:contrib:${repo}`;
  const cached = sessionStorage.getItem(key);
  if (cached) {
    try { return JSON.parse(cached); } catch (_) { /* fall through */ }
  }
  const res = await fetch(`https://api.github.com/repos/${repo}/contributors?per_page=100`, {
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const raw = await res.json();
  const data = (Array.isArray(raw) ? raw : [])
    .filter((c) => c && c.type === "User" && !/\[bot\]$/i.test(c.login))
    .map((c) => ({
      login: c.login,
      avatar_url: c.avatar_url,
      html_url: c.html_url,
      contributions: c.contributions,
    }));
  try { sessionStorage.setItem(key, JSON.stringify(data)); } catch (_) { /* quota */ }
  return data;
}

// ─── GitHub API: org repos (cached per session) ────
async function fetchOrgRepos(org = "omicverse") {
  const key = `gh:org-repos:${org}`;
  const cached = sessionStorage.getItem(key);
  if (cached) {
    try { return JSON.parse(cached); } catch (_) { /* fall through */ }
  }
  let raw = [];
  try {
    const res = await fetch(`https://api.github.com/orgs/${org}/repos?per_page=100&type=public`, {
      headers: { Accept: "application/vnd.github+json" },
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    raw = await res.json();
  } catch (_) {
    const res = await fetch("assets/packages.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`manifest HTTP ${res.status}`);
    raw = await res.json();
  }
  const data = (Array.isArray(raw) ? raw : []).map((r) => ({
    name: r.name,
    full_name: r.full_name,
    html_url: r.html_url,
    description: r.description,
    language: r.language,
    stargazers_count: r.stargazers_count,
    size: r.size,
    archived: r.archived,
    fork: r.fork,
    pushed_at: r.pushed_at,
    default_branch: r.default_branch,
    logo_url: r.logo_url,
  }));
  try { sessionStorage.setItem(key, JSON.stringify(data)); } catch (_) { /* quota */ }
  return data;
}

// Categorize a repo into a role + filter tags.
// Returns null for repos that should be hidden from the package catalog.
function categorizeRepo(repo) {
  const name = repo.name;
  const skip = new Set([".github", "omicverse", "omicverse-pages", "omicverse-org-home"]);
  if (skip.has(name) || repo.archived || repo.size === 0) return null;
  if (name === "omicverse") {
    return { tags: "core python", role: "Core API", lang: "Python", weight: 0 };
  }
  if (name === "anndata-oom") {
    return { tags: "data rust", role: "Data foundation", lang: "Rust", weight: 1 };
  }
  if (name === "omicverse-skills" || name === "omicclaw") {
    return { tags: "agent python", role: "Agent skill", lang: "Python", weight: 2 };
  }
  if (/^py-/i.test(name)) {
    return { tags: "python port", role: "Method port", lang: "Python", weight: 3 };
  }
  if (/^rust-/i.test(name)) {
    return { tags: "rust port", role: "Method port", lang: "Rust", weight: 3 };
  }
  // tutorials, plugins, ontology mappers, etc.
  return { tags: "tools", role: "Tool", lang: repo.language || "—", weight: 4 };
}

// Sort: by category weight, then stars desc, then name asc.
function sortRepos(items) {
  return items.sort((a, b) => {
    if (a.cat.weight !== b.cat.weight) return a.cat.weight - b.cat.weight;
    const sa = a.repo.stargazers_count || 0;
    const sb = b.repo.stargazers_count || 0;
    if (sa !== sb) return sb - sa;
    return a.repo.name.localeCompare(b.repo.name);
  });
}

function packageLogoGroup(repo, cat) {
  const tags = cat.tags.split(/\s+/);
  if (tags.includes("core") || tags.includes("data") || tags.includes("agent")) return "Core / Data / Agent";
  if (/^py-/i.test(repo.name)) return "Python ports";
  if (/^rust-/i.test(repo.name)) return "Rust ports";
  return "Tools / Tutorials";
}

async function renderPackageLogoRows() {
  const container = document.querySelector("[data-package-logo-rows]");
  if (!container) return;
  try {
    const repos = await fetchOrgRepos();
    const items = sortRepos(
      repos
        .map((r) => ({ repo: r, cat: categorizeRepo(r) }))
        .filter((x) => x.cat !== null),
    );
    const groups = ["Core / Data / Agent", "Python ports", "Rust ports", "Tools / Tutorials"]
      .map((name) => ({
        name,
        items: items.filter(({ repo, cat }) => packageLogoGroup(repo, cat) === name),
      }))
      .filter((group) => group.items.length > 0);

    container.innerHTML = groups
      .map((group) => `<div class="package-logo-row">
        <div class="package-logo-row-label">${escapeHtml(group.name)}</div>
        <div class="package-logo-row-items">
          ${group.items.map(({ repo }) => {
            const logo = escapeHtml(repoLogoUrl(repo));
            return `<a class="package-logo-link" href="${repo.html_url}" target="_blank" rel="noopener" title="${escapeHtml(repo.name)}" aria-label="${escapeHtml(repo.name)}">
              <img data-repo-logo src="${logo}" alt="" loading="eager" />
            </a>`;
          }).join("")}
        </div>
      </div>`)
      .join("");
    bindRepoLogoErrors(container);
  } catch (_) {
    container.innerHTML = `<p class="fetch-error">Couldn't load package logos.</p>`;
  }
}
renderPackageLogoRows();

function packageWord(count) {
  return count === 1 ? "package" : "packages";
}

function updatePackageStackNumbers(root, repos) {
  const visibleRepos = repos.filter((repo) => categorizeRepo(repo) !== null);
  const core = repos.find((repo) => repo.name === "omicverse");
  const agentCount = visibleRepos.filter((repo) => {
    const cat = categorizeRepo(repo);
    return cat && cat.tags.split(/\s+/).includes("agent");
  }).length;
  const pythonPortCount = visibleRepos.filter((repo) => /^py-/i.test(repo.name)).length;
  const rustPortCount = visibleRepos.filter((repo) => /^rust-/i.test(repo.name)).length;

  root.querySelectorAll("[data-layer-index]").forEach((node, index) => {
    node.textContent = `/ ${String(index + 1).padStart(2, "0")}`;
  });

  const agentLabel = root.querySelector("[data-stack-agent-label]");
  if (agentLabel) agentLabel.textContent = `Agent layer · ${agentCount}`;

  const coreLabel = root.querySelector("[data-stack-core-label]");
  if (coreLabel && core) coreLabel.textContent = `Core API · ${core.stargazers_count}★`;

  const pythonLabel = root.querySelector("[data-stack-python-label]");
  if (pythonLabel) {
    pythonLabel.textContent = `${pythonPortCount} ${packageWord(pythonPortCount)} · pure-python re-implementations`;
  }

  const rustLabel = root.querySelector("[data-stack-rust-label]");
  if (rustLabel) {
    rustLabel.textContent = `${rustPortCount} ${packageWord(rustPortCount)} · 10–200× faster, bit-identical`;
  }
}

async function renderPackageStack() {
  const holder = document.querySelector("[data-packages-network]");
  if (!holder) return;

  try {
    const [svgRes, repos] = await Promise.all([
      fetch(holder.dataset.src || "assets/packages-network.svg"),
      fetchOrgRepos(),
    ]);
    if (!svgRes.ok) throw new Error(`SVG HTTP ${svgRes.status}`);
    holder.innerHTML = await svgRes.text();
    updatePackageStackNumbers(holder, repos);
  } catch (_) {
    try {
      const repos = await fetchOrgRepos();
      updatePackageStackNumbers(holder, repos);
    } catch (_) {
      // Keep the static SVG fallback when live data is unavailable.
    }
  }
}
renderPackageStack();

// ─── Packages page: dynamic list ──────────────────
async function renderOrgRepos() {
  const container = document.querySelector("[data-org-repos]");
  if (!container) return;
  try {
    const repos = await fetchOrgRepos();
    const items = sortRepos(
      repos
        .map((r) => ({ repo: r, cat: categorizeRepo(r) }))
        .filter((x) => x.cat !== null),
    );
    container.innerHTML = items
      .map(({ repo, cat }) => {
        const desc = repo.description
          ? escapeHtml(repo.description)
          : '<em style="color:var(--muted);">no description</em>';
        const stars =
          repo.stargazers_count >= 5
            ? ` · ${repo.stargazers_count}★`
            : "";
        const logo = escapeHtml(repoLogoUrl(repo));
        return `<a data-tags="${cat.tags}" href="${repo.html_url}" target="_blank" rel="noopener">
            <span class="t-logo"><img data-repo-logo src="${logo}" alt="" loading="eager" /></span>
            <span class="t-name">${escapeHtml(repo.name)}</span>
            <span class="t-desc">${desc}</span>
            <span class="t-tag">${escapeHtml(cat.role)} · ${escapeHtml(cat.lang)}${stars}</span>
        </a>`;
      })
      .join("");
    bindRepoLogoErrors(container);
    // re-bind filter to the freshly rendered nodes
    bindPackageFilter();
  } catch (err) {
    container.innerHTML = `<p class="fetch-error">Couldn't load the live package list.
      <a href="https://github.com/omicverse" target="_blank" rel="noopener">View the org on GitHub →</a></p>`;
  }
}
renderOrgRepos();

// ─── People page: avatar grid + ecosystem maintainers ──
function renderAvatarGrid(grid, contributors) {
  if (!contributors.length) {
    grid.innerHTML = `<p class="fetch-error">No contributors found yet.</p>`;
    return;
  }
  const max = parseInt(grid.dataset.max || "60", 10);
  const visible = contributors.slice(0, max);
  const remaining = contributors.length - visible.length;
  const html = visible
    .map(
      (c) => `<a href="${c.html_url}" target="_blank" rel="noopener"
        title="${escapeHtml(c.login)} · ${c.contributions} commit${c.contributions === 1 ? "" : "s"}"
        aria-label="${escapeHtml(c.login)}">
        <img src="${c.avatar_url}&s=80" alt="" loading="lazy" />
      </a>`,
    )
    .join("");
  grid.innerHTML = html + (remaining > 0 ? `<span class="more">+${remaining}</span>` : "");
}

function showFetchError(el, repo) {
  el.innerHTML = `<p class="fetch-error">Couldn't load live data.
    <a href="https://github.com/${repo}" target="_blank" rel="noopener">View on GitHub →</a></p>`;
}

// 1) Avatar grid for the main repo
document.querySelectorAll(".avatar-grid[data-repo]").forEach(async (grid) => {
  const repo = grid.dataset.repo;
  try {
    const contributors = await fetchContributors(repo);
    renderAvatarGrid(grid, contributors);
  } catch (err) {
    showFetchError(grid, repo);
  }
});

// 2) Other public repositories — leading public contributor per repo.
async function fetchOtherRepoMaintainers() {
  const repos = await fetchOrgRepos();
  const items = sortRepos(
    repos
      .map((r) => ({ repo: r, cat: categorizeRepo(r) }))
      .filter((x) => x.cat !== null && x.repo.name !== "omicverse" && !x.repo.fork),
  );

  const rows = await Promise.all(
    items.map(async ({ repo, cat }) => {
      try {
        const contributors = await fetchContributors(repo.full_name);
        const lead = contributors[0];
        if (!lead) return null;
        return { repo, cat, lead };
      } catch (_) {
        return null;
      }
    }),
  );

  return rows.filter(Boolean);
}

function renderOtherRepoMaintainers() {
  const list = document.querySelector("[data-other-repo-maintainers]");
  if (!list) return;

  fetchOtherRepoMaintainers()
    .then((items) => {
      if (!items.length) {
        list.innerHTML = `<p class="fetch-error">No public repository contributors found yet.</p>`;
        return;
      }

      list.innerHTML = items
        .map(({ repo, cat, lead }) => {
          const repoUrl = `https://github.com/${repo.full_name}`;
          return `<div class="row">
            <div class="avatar">
              <img src="${lead.avatar_url}${lead.avatar_url.includes("?") ? "&" : "?"}s=80" alt="" loading="lazy" />
            </div>
            <div class="pkg">
              ${escapeHtml(repo.name)}
              <span class="role">${escapeHtml(cat.role)}</span>
            </div>
            <div class="who">
              <span class="login">${escapeHtml(lead.login)}</span>
              <span class="commits">${lead.contributions} commit${lead.contributions === 1 ? "" : "s"}</span>
            </div>
            <div class="links">
              <a href="${lead.html_url}" target="_blank" rel="noopener">GitHub</a>
              ·
              <a href="${repoUrl}" target="_blank" rel="noopener">Repo →</a>
            </div>
          </div>`;
        })
        .join("");
    })
    .catch(() => {
      list.innerHTML = `<p class="fetch-error">Couldn't load other repository maintainers.
        <a href="https://github.com/omicverse?tab=repositories" target="_blank" rel="noopener">View repositories →</a></p>`;
    });
}
renderOtherRepoMaintainers();
