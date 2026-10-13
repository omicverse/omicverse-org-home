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
      const holder = img.closest(".t-logo");
      if (holder) holder.classList.add("is-missing-logo");
      else img.remove();
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
  const key = `gh:org-repos:${org}:paginated-v1`;
  const cached = sessionStorage.getItem(key);
  if (cached) {
    try { return JSON.parse(cached); } catch (_) { /* fall through */ }
  }
  let raw = [];
  try {
    for (let page = 1; ; page += 1) {
      const res = await fetch(`https://api.github.com/orgs/${org}/repos?per_page=100&type=public&page=${page}`, {
        headers: { Accept: "application/vnd.github+json" },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const batch = await res.json();
      raw.push(...batch);
      if (batch.length < 100) break;
    }
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
