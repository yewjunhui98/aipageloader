const API_BASE = window.location.hostname === "localhost" ? "http://localhost:8000" : "http://backend:8000";
const ACTIVE_USER_KEY = "active-dashboard-user";

const state = {
  userId: null,
  username: null,
  currentUrl: null,
  pages: [],
  preloadCache: new Map(),
  lastPredictions: [],
  visitCount: 0,
};

const usernameEl = document.getElementById("username");
const existingUsersEl = document.getElementById("existing-users");
const userStateEl = document.getElementById("user-state");
const pageButtonsEl = document.getElementById("page-buttons");
const predictionsEl = document.getElementById("predictions");
const historyEl = document.getElementById("history");
const cacheListEl = document.getElementById("cache-list");
const metricUserEl = document.getElementById("metric-user");
const metricVisitsEl = document.getElementById("metric-visits");
const metricCacheEl = document.getElementById("metric-cache");
const metricConfidenceEl = document.getElementById("metric-confidence");

document.getElementById("create-user").addEventListener("click", createOrLoadUser);
document.getElementById("load-selected-user").addEventListener("click", loadSelectedUser);
pageButtonsEl.addEventListener("click", onPageButtonClick);
pageButtonsEl.addEventListener("mouseover", onNavigateIntent);
pageButtonsEl.addEventListener("focusin", onNavigateIntent);

bootstrap();

async function bootstrap() {
  await loadPages();
  await loadExistingUsers();
  renderPredictions([]);
  renderCache();
  setNavigationEnabled(false);
  clearActiveUserOnManualRefresh();
  await restoreActiveUser();
  updateMetrics();
}

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`API ${path} failed: ${detail}`);
  }

  return response.json();
}

async function loadPages() {
  state.pages = await api("/api/pages");
  pageButtonsEl.innerHTML = state.pages
    .map(
      (page) =>
        `<button class="nav-page-btn" data-url="${page.url}" data-title="${page.title}" data-route="${getPageRoute(page.title)}">${page.title}</button>`
    )
    .join("");
}

async function createOrLoadUser() {
  const username = usernameEl.value.trim();
  if (!username) {
    userStateEl.textContent = "Enter a username first.";
    return;
  }

  const user = await api("/api/users", {
    method: "POST",
    body: JSON.stringify({ username }),
  });
  await loadExistingUsers(user.id);
  await activateUser(user.id, user.username);
}

async function loadSelectedUser() {
  const selectedId = Number(existingUsersEl.value);
  if (!selectedId) {
    userStateEl.textContent = "Select an existing user first.";
    return;
  }
  const username = existingUsersEl.options[existingUsersEl.selectedIndex]?.text || `user-${selectedId}`;
  await activateUser(selectedId, username);
}

async function loadExistingUsers(selectedUserId = null) {
  const users = await api("/api/users");
  existingUsersEl.innerHTML = "<option value=\"\">Select existing user</option>";
  for (const user of users) {
    const option = document.createElement("option");
    option.value = String(user.id);
    option.textContent = user.username;
    existingUsersEl.appendChild(option);
  }
  if (selectedUserId) {
    existingUsersEl.value = String(selectedUserId);
  }
}

async function activateUser(userId, username) {
  state.preloadCache.clear();
  state.lastPredictions = [];
  renderCache();
  renderPredictions([]);
  setNavigationEnabled(true);

  state.userId = userId;
  state.username = username;
  sessionStorage.setItem(ACTIVE_USER_KEY, JSON.stringify({ userId, username }));
  userStateEl.innerHTML = `<span class="ok">Active user: ${username} (id=${userId})</span>`;
  const history = await refreshHistory();
  if (history.length) {
    state.currentUrl = history[0].url;
    await hydratePredictionsFromDb();
    applyNavigatePriority(state.lastPredictions);
  } else {
    state.currentUrl = null;
    state.lastPredictions = [];
    renderPredictions([]);
  }
  updateMetrics();
}

async function onPageButtonClick(event) {
  const button = event.target.closest(".nav-page-btn");
  if (!button) return;
  await visitPage(button.dataset.url, button.dataset.title, button.dataset.route);
}

function onNavigateIntent(event) {
  if (!state.userId) return;
  const button = event.target.closest(".nav-page-btn");
  if (!button) return;
  if (!isPredictedRoute(button.dataset.route)) return;
  preloadViaLink(button.dataset.route, button.dataset.title);
}

async function visitPage(pageUrl, pageTitle, pageRoute) {
  if (!state.userId) {
    userStateEl.textContent = "Create/load a user first.";
    return;
  }
  preloadViaLink(pageRoute, pageTitle);

  await api("/api/visit", {
    method: "POST",
    body: JSON.stringify({
      user_id: state.userId,
      page_url: pageUrl,
      page_title: pageTitle,
    }),
  });

  state.currentUrl = pageUrl;
  const nextResult = await api(
    `/api/predict-next/${state.userId}?current_url=${encodeURIComponent(state.currentUrl)}&top_k=3`
  );
  state.lastPredictions = prioritizePredictions(nextResult.predictions || []);
  window.location.href = pageRoute;
}

async function predictAndPreload() {
  const result = await api(
    `/api/predict-next/${state.userId}?current_url=${encodeURIComponent(state.currentUrl)}&top_k=3`
  );
  const prioritized = prioritizePredictions(result.predictions || []);
  state.lastPredictions = prioritized;
  renderPredictions(prioritized);
  applyNavigatePriority(prioritized);
  renderCache();
  updateMetrics();
}

async function refreshHistory() {
  if (!state.userId) {
    historyEl.innerHTML = "<li>No user selected.</li>";
    return;
  }

  const history = await api(`/api/history/${state.userId}`);
  state.visitCount = history.length;
  historyEl.innerHTML = history.length
    ? history
        .slice(0, 8)
        .map((item) => `<li>${item.title} (${new Date(item.visited_at).toLocaleTimeString()})</li>`)
        .join("")
    : "<li>No visits yet.</li>";
  updateMetrics();
  return history;
}

function renderCache() {
  const cachedEntries = Array.from(state.preloadCache.entries());
  cacheListEl.innerHTML = cachedEntries.length
    ? cachedEntries.map(([route, title]) => `<li>${title} (${route})</li>`).join("")
    : "<li>Nothing preloaded yet.</li>";
}

function renderPredictions(predictions) {
  if (!predictions.length) {
    predictionsEl.innerHTML = "<p>No prediction yet. Visit more pages to train model.</p>";
    return;
  }

  predictionsEl.innerHTML = predictions
    .map((p) => {
      const percent = (p.probability * 100).toFixed(1);
      return `
        <article class="prediction-row">
          <div class="prediction-topline">
            <strong>${toPageName(p.url)}</strong>
            <span class="probability">${percent}%</span>
          </div>
          <div class="prediction-url">Visited: ${p.visit_count ?? 0} times</div>
          <div class="prediction-url">${p.url}</div>
          <div class="meter"><span style="width:${percent}%"></span></div>
        </article>
      `;
    })
    .join("");
}

function updateMetrics() {
  metricUserEl.textContent = state.username ?? "-";
  metricVisitsEl.textContent = String(state.visitCount);
  metricCacheEl.textContent = String(state.preloadCache.size);
  const topProbability = state.lastPredictions[0]?.probability ?? 0;
  metricConfidenceEl.textContent = `${(topProbability * 100).toFixed(1)}%`;
}

function toPageName(url) {
  const page = state.pages.find((p) => p.url === url);
  if (page) return page.title;
  return url.split("/").pop() || url;
}

async function hydratePredictionsFromDb() {
  if (!state.userId || !state.currentUrl) return;
  const stored = await api(
    `/api/stored-prediction/${state.userId}?current_url=${encodeURIComponent(state.currentUrl)}`
  );
  state.lastPredictions = prioritizePredictions(stored.predictions || []);
  renderPredictions(state.lastPredictions);
  applyNavigatePriority(state.lastPredictions);
  updateMetrics();
}

function prioritizePredictions(predictions) {
  return [...predictions].sort((a, b) => {
    const visitDiff = (b.visit_count ?? 0) - (a.visit_count ?? 0);
    if (visitDiff !== 0) return visitDiff;
    return (b.probability ?? 0) - (a.probability ?? 0);
  });
}

function applyNavigatePriority(predictions) {
  if (!predictions.length) return;
  const weighted = new Map(predictions.map((p, idx) => [p.url, idx]));
  const buttons = [...pageButtonsEl.querySelectorAll(".nav-page-btn")];
  buttons.sort((a, b) => {
    const aIdx = weighted.has(a.dataset.url) ? weighted.get(a.dataset.url) : Number.MAX_SAFE_INTEGER;
    const bIdx = weighted.has(b.dataset.url) ? weighted.get(b.dataset.url) : Number.MAX_SAFE_INTEGER;
    return aIdx - bIdx;
  });
  pageButtonsEl.innerHTML = "";
  for (const button of buttons) {
    pageButtonsEl.appendChild(button);
  }
  for (const p of predictions) {
    const title = toPageName(p.url);
    preloadViaLink(getPageRoute(title), title);
  }
}

function setNavigationEnabled(enabled) {
  const buttons = pageButtonsEl.querySelectorAll(".nav-page-btn");
  for (const button of buttons) {
    button.disabled = !enabled;
  }
}

function isPredictedRoute(route) {
  if (!state.lastPredictions.length) return false;
  const predictedRoutes = new Set(state.lastPredictions.map((p) => getPageRoute(toPageName(p.url))));
  return predictedRoutes.has(route);
}

async function restoreActiveUser() {
  const raw = sessionStorage.getItem(ACTIVE_USER_KEY);
  if (!raw) return;
  try {
    const saved = JSON.parse(raw);
    const savedId = Number(saved.userId);
    if (!savedId) return;
    const option = [...existingUsersEl.options].find((opt) => Number(opt.value) === savedId);
    if (!option) {
      sessionStorage.removeItem(ACTIVE_USER_KEY);
      return;
    }
    existingUsersEl.value = String(savedId);
    await activateUser(savedId, saved.username || option.textContent || `user-${savedId}`);
  } catch (_err) {
    sessionStorage.removeItem(ACTIVE_USER_KEY);
  }
}

function clearActiveUserOnManualRefresh() {
  const navEntry = performance.getEntriesByType("navigation")[0];
  if (navEntry && navEntry.type === "reload") {
    sessionStorage.removeItem(ACTIVE_USER_KEY);
  }
}

function preloadViaLink(pageRoute, pageTitle) {
  if (!pageRoute) return;
  const href = pageRoute;
  const existing = document.querySelector(`link[data-preload-href="${href}"]`);
  if (existing) {
    if (!state.preloadCache.has(pageRoute)) {
      state.preloadCache.set(pageRoute, pageTitle || pageRoute);
      renderCache();
      updateMetrics();
    }
    return;
  }
  const link = document.createElement("link");
  link.rel = "preload";
  link.as = "document";
  link.href = href;
  link.dataset.preloadHref = href;
  document.head.appendChild(link);
  state.preloadCache.set(pageRoute, pageTitle || pageRoute);
  renderCache();
  updateMetrics();
}

function getPageRoute(pageTitle) {
  const slug = (pageTitle || "page")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return `./pages/${slug}.html`;
}
