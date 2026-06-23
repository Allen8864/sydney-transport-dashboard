const els = {
  clock: document.getElementById("clock"),
  date: document.getElementById("date"),
  temp: document.getElementById("temp"),
  feels: document.getElementById("feels"),
  rain: document.getElementById("rain"),
  wind: document.getElementById("wind"),
  humidity: document.getElementById("humidity"),
  summary: document.getElementById("summary"),
  hours: document.getElementById("hours"),
  stops: document.getElementById("stops"),
};

let trainAlertTickerTimer = null;
let trainAlertTickerIndex = 0;
let resizeTimer = null;
let lastTransport = null;
let renderedDirectionalRowCount = null;
let renderedTrainSecondaryRowCount = null;

const DESKTOP_MEDIA_QUERY = "(min-width: 1201px)";
const DESKTOP_DIRECTIONAL_ROW_COUNT = 8;
const COMPACT_DIRECTIONAL_ROW_COUNT = 4;
const DESKTOP_TRAIN_SECONDARY_ROW_COUNT = 3;
const COMPACT_TRAIN_SECONDARY_ROW_COUNT = 2;
const GENERIC_DEPARTURE_ROW_COUNT = 5;

function value(v, suffix = "") {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  return `${Math.round(v)}${suffix}`;
}

function metricValue(v, suffix = "") {
  if (v === null || v === undefined || Number.isNaN(v)) return "--";
  const rounded = Math.round(v);
  return `${rounded}${suffix ? `<small>${suffix}</small>` : ""}`;
}

function renderWeather(weather) {
  els.hours.classList.remove("skeleton");
  els.hours.removeAttribute("aria-hidden");
  if (!weather) {
    els.summary.textContent = "";
    els.summary.className = "summary weather-icon weather-icon-unavailable";
    els.summary.title = "Weather unavailable";
    els.summary.setAttribute("aria-label", "Weather unavailable");
    return;
  }
  els.temp.textContent = value(weather.temp);
  els.feels.innerHTML = metricValue(weather.feels, "°");
  els.rain.innerHTML = metricValue(weather.rain, "mm");
  els.wind.innerHTML = metricValue(weather.wind);
  els.humidity.innerHTML = metricValue(weather.humidity, "%");
  els.summary.textContent = "";
  els.summary.className = `summary weather-icon ${weatherIconClass(weather.icon)}`;
  els.summary.title = weather.summary || "Weather";
  els.summary.setAttribute("aria-label", weather.summary || "Weather");
  els.hours.innerHTML = (weather.hourly || []).slice(0, 8).map((hour) => `
    <div class="hour">
      <b>${hour.time}</b>
      <span class="deg">${value(hour.temp, "°")}</span>
      <span>${value(hour.rainChance, "%")} rain</span>
    </div>
  `).join("");
}

function weatherIconClass(icon) {
  switch (icon) {
    case "☀":
      return "weather-icon-clear";
    case "◐":
      return "weather-icon-partly";
    case "☁":
      return "weather-icon-cloud";
    case "≋":
      return "weather-icon-fog";
    case "☂":
      return "weather-icon-rain";
    case "⚡":
      return "weather-icon-storm";
    default:
      return "weather-icon-unavailable";
  }
}

function renderStops(transport) {
  lastTransport = transport;
  const directionalLimit = directionalRowCount();
  const trainSecondaryLimit = trainSecondaryRowCount();
  renderedDirectionalRowCount = directionalLimit;
  renderedTrainSecondaryRowCount = trainSecondaryLimit;
  const stops = (transport && transport.stops) || [];
  els.stops.classList.remove("skeleton");
  els.stops.removeAttribute("aria-hidden");
  els.stops.innerHTML = stops.map((stop) => {
    if (stop.error) {
      return `
        <article class="stop ${stop.mode || ""}">
          <div class="stop-head">
            <div class="stop-name">${escapeHtml(stop.name)}</div>
            <div class="kind">${escapeHtml(stop.kind)}</div>
          </div>
          <div class="error">${escapeHtml(stop.error)}</div>
        </article>
      `;
    }
    if (stop.mode === "train_platforms") {
      return renderTrainPlatformBoard(stop, trainSecondaryLimit);
    }
    if (stop.mode === "metro" || stop.mode === "light_rail") {
      return renderDirectionalStop(stop, directionalLimit);
    }
    const rows = (stop.departures || []).slice(0, GENERIC_DEPARTURE_ROW_COUNT);
    return `
      <article class="stop ${stop.mode || ""}">
        <div class="stop-head">
          <div class="stop-name">${escapeHtml(stop.name)}</div>
          <div class="kind">${escapeHtml(stop.kind)}</div>
        </div>
        <div>
          ${rows.length ? rows.map((row) => renderDeparture(row, stop.mode)).join("") : '<div class="empty">No departures</div>'}
        </div>
      </article>
    `;
  }).join("");
  startTrainAlertTicker();
  syncStopTickers();
}

function directionalRowCount() {
  return window.matchMedia(DESKTOP_MEDIA_QUERY).matches
    ? DESKTOP_DIRECTIONAL_ROW_COUNT
    : COMPACT_DIRECTIONAL_ROW_COUNT;
}

function trainSecondaryRowCount() {
  return window.matchMedia(DESKTOP_MEDIA_QUERY).matches
    ? DESKTOP_TRAIN_SECONDARY_ROW_COUNT
    : COMPACT_TRAIN_SECONDARY_ROW_COUNT;
}

function renderTrainPlatformBoard(stop, secondaryLimit) {
  const platforms = stop.platforms || stop.departures || [];
  return `
    <article class="stop train-platforms">
      ${renderTrainBoardHeader(stop)}
      <div class="platform-board">
        ${platforms.map((platform) => renderTrainPlatformCard(platform, secondaryLimit)).join("")}
      </div>
    </article>
  `;
}

function renderTrainBoardHeader(stop) {
  const alerts = (stop.alerts || []).filter(Boolean).map(normalizeTrainAlert);
  const alertLabel = alerts.map((alert) => `${(alert.badges || []).join(" ")} ${alert.text}`.trim()).join(" | ");
  return `
    <div class="stop-head train-board-head">
      <div class="stop-name">${escapeHtml(stop.name)}</div>
      ${alerts.length ? `
        <div class="train-alert-ticker" aria-label="${escapeHtml(alertLabel)}" data-alert-count="${alerts.length}">
          <div class="train-alert-track">
            ${alerts.map((alert, index) => renderTrainAlertItem(alert, index === 0)).join("")}
          </div>
        </div>
      ` : '<div class="kind">Central Platforms</div>'}
    </div>
  `;
}

function normalizeTrainAlert(alert) {
  if (typeof alert === "string") return { text: alert, badges: [] };
  return {
    text: alert.text || "",
    badges: Array.isArray(alert.badges) ? alert.badges.filter(Boolean) : [],
  };
}

function renderTrainAlertItem(alert, active) {
  return `
    <div class="train-alert-item${active ? " is-active" : ""}">
      ${(alert.badges || []).map((badge) => `<span class="train-alert-badge">${escapeHtml(badge)}</span>`).join("")}
      <span>${escapeHtml(alert.text)}</span>
    </div>
  `;
}

function startTrainAlertTicker() {
  if (trainAlertTickerTimer) {
    clearInterval(trainAlertTickerTimer);
    trainAlertTickerTimer = null;
  }
  trainAlertTickerIndex = 0;
  const ticker = document.querySelector(".train-alert-ticker");
  if (!ticker) return;
  const items = ticker.querySelectorAll(".train-alert-item");
  if (items.length <= 1) return;
  trainAlertTickerTimer = setInterval(() => {
    trainAlertTickerIndex = (trainAlertTickerIndex + 1) % items.length;
    for (let i = 0; i < items.length; i += 1) {
      if (i === trainAlertTickerIndex) {
        items[i].classList.add("is-active");
      } else {
        items[i].classList.remove("is-active");
      }
    }
  }, 5000);
}

function renderTrainPlatformCard(platform, secondaryLimit) {
  const rows = (platform.departures || []).slice(0, secondaryLimit + 1);
  const primary = rows[0];
  const secondary = rows.slice(1);
  return `
    <section class="platform-card" style="--secondary-row-count: ${secondaryLimit}">
      ${renderTrainPlatformHeader(platform)}
      ${renderPrimaryTrainSlot(platform, primary)}
      ${renderSecondaryTrainRows(secondary, secondaryLimit)}
    </section>
  `;
}

function renderTrainPlatformHeader(platform) {
  return `
    <header class="platform-card-head">
      <div class="platform-number">${escapeHtml(platform.name || platform.id)}</div>
      <div>
        <div class="platform-kind">
          <span>${escapeHtml(platform.kind || "Central")}</span>
          ${renderLineBadges(platform.hint)}
        </div>
      </div>
    </header>
  `;
}

function renderLineBadges(hint) {
  return String(hint || "").split("/")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => `<span class="line-badge">${escapeHtml(part)}</span>`)
    .join("");
}

function renderPrimaryTrainSlot(platform, primary) {
  return primary ? renderPrimaryTrain(primary) : renderPrimaryTrainPlaceholder(platform);
}

function renderPrimaryTrainPlaceholder(platform) {
  if (platform.status) {
    return `
      <div class="train-primary train-primary-placeholder">
        <div class="platform-status">
          <div class="status-mark">!</div>
          <div>${escapeHtml(platform.status)}</div>
        </div>
      </div>
    `;
  }
  return '<div class="train-primary train-primary-placeholder"><div class="empty platform-empty">No departures</div></div>';
}

function renderPrimaryTrain(row) {
  const stops = Array.isArray(row.stops) ? row.stops.filter(Boolean) : [];
  return `
    <div class="train-primary">
      <div class="train-main">
        <div class="route">${escapeHtml(shortLine(row.line))}</div>
        <div class="train-headsign">${escapeHtml(row.destination || "Destination unavailable")}</div>
        ${renderServiceBadge(row.service)}
      </div>
      ${stops.length ? renderStopTicker(stops) : renderEmptyStopTicker()}
      <div class="train-due">${renderDue(row)}</div>
    </div>
  `;
}

function renderEmptyStopTicker() {
  return '<div class="train-destination is-empty" aria-hidden="true">&nbsp;</div>';
}

function renderStopTicker(stops) {
  const stopRowHeight = 20;
  const listHeight = Math.max(1, stops.length) * stopRowHeight;
  const stopItems = stops.map((stop) => `<div class="train-stop">${escapeHtml(stop)}</div>`).join("");
  return `
    <div class="train-stop-ticker" aria-label="${escapeHtml(stops.join(", "))}" data-stop-count="${stops.length}" style="--stop-list-height: ${listHeight}px; --stop-scroll-distance: 0px">
      <div class="train-stop-track">
        <div class="train-stop-list">${stopItems}</div>
      </div>
    </div>
  `;
}

function syncStopTickers() {
  document.querySelectorAll(".train-stop-ticker").forEach((ticker) => {
    const rowHeight = parseFloat(getComputedStyle(ticker).getPropertyValue("--train-stop-row-height")) || 20;
    const stopCount = Number(ticker.dataset.stopCount || 0);
    const viewportHeight = ticker.clientHeight;
    if (!stopCount || !viewportHeight) return;
    const listHeight = stopCount * rowHeight;
    const visibleRows = Math.max(1, Math.floor(viewportHeight / rowHeight));
    const scrollDistance = Math.max(0, listHeight - visibleRows * rowHeight);
    const scrollRows = Math.max(1, stopCount - visibleRows);
    const track = ticker.querySelector(".train-stop-track");
    ticker.style.setProperty("--stop-list-height", `${listHeight}px`);
    ticker.style.setProperty("--stop-scroll-distance", `-${scrollDistance}px`);
    if (track) {
      track.style.animationName = scrollDistance > 0 ? "train-stop-scroll" : "none";
      track.style.animationDuration = `${Math.max(12, scrollRows * 1.8)}s`;
      track.style.animationTimingFunction = `steps(${scrollRows}, end)`;
    }
  });
}

function renderSecondaryTrainRows(rows, rowLimit) {
  const cells = rows.slice(0, rowLimit).map((row) => renderSecondaryTrainRow(row));
  while (cells.length < rowLimit) {
    cells.push(renderEmptySecondaryTrainRow());
  }
  return `<div class="platform-secondary" style="grid-template-rows: repeat(${rowLimit}, minmax(0, 1fr))">${cells.join("")}</div>`;
}

function renderSecondaryTrainRow(row) {
  return `
    <div class="train-next-row">
      <div class="route">${escapeHtml(shortLine(row.line))}</div>
      <div class="dest">${escapeHtml(row.destination || "Destination unavailable")}</div>
      ${renderServiceBadge(row.service, "small")}
      <div class="due">${renderDue(row)}</div>
    </div>
  `;
}

function renderServiceBadge(service, size = "") {
  const text = String(service || "").trim();
  const classes = ["service-badge", size].filter(Boolean).join(" ");
  if (!text) {
    return `<div class="${classes} is-hidden" aria-hidden="true">&nbsp;</div>`;
  }
  return `<div class="${classes}">${escapeHtml(text)}</div>`;
}

function renderEmptySecondaryTrainRow() {
  return '<div class="train-next-row is-empty" aria-hidden="true"><div class="route">&nbsp;</div><div class="dest">&nbsp;</div><div class="service-badge small">&nbsp;</div><div class="due">&nbsp;</div></div>';
}

function renderDue(row) {
  return `${escapeHtml(formatDue(row.due))}<small>m</small>`;
}

function formatDue(due) {
  return due === null || due === undefined ? "--" : due;
}

function renderDirectionalStop(stop, rowLimit) {
  const groups = directionalGroups(stop);
  const boardNotice = directionalBoardNotice(stop, groups);
  return `
    <article class="stop directional ${stop.mode || ""}">
      <div class="stop-head">
        <div class="stop-name">${escapeHtml(stop.name)}</div>
        <div class="kind">${escapeHtml(stop.kind)}</div>
      </div>
      <div class="direction-grid">
        ${boardNotice ? renderBoardNotice(boardNotice) : groups.map((group) => renderDirectionColumn(group, rowLimit)).join("")}
      </div>
    </article>
  `;
}

function directionalGroups(stop) {
  if (Array.isArray(stop.directions) && stop.directions.length) {
    return stop.directions.map((direction) => ({
      id: direction.id,
      title: direction.title,
      rows: direction.departures || [],
      notice: direction.notice || null,
    }));
  }
  const rows = stop.departures || [];
  return [{ id: "default", title: stop.name, rows, notice: null }];
}

function directionalBoardNotice(stop, groups) {
  const hasRows = groups.some((group) => group.rows.length);
  if (stop.notice) return stop.notice;
  if (stop.status && !hasRows) return stop.status;
  return null;
}

function renderDirectionColumn(group, rowLimit) {
  const bodyStyle = group.notice ? "" : ` style="grid-template-rows: repeat(${rowLimit}, minmax(0, 1fr))"`;
  return `
    <section class="direction" aria-label="${escapeHtml(group.title)}">
      <div class="direction-title">${escapeHtml(group.title)}</div>
      <div class="direction-body ${group.notice ? "has-column-notice" : ""}"${bodyStyle}>
        ${group.notice ? renderColumnNotice(group.notice) : renderDepartureCells(group.rows, rowLimit)}
      </div>
    </section>
  `;
}

function renderDepartureCells(rows, rowLimit) {
  const cells = rows.slice(0, rowLimit).map((row) => renderCompactDeparture(row));
  while (cells.length < rowLimit) {
    cells.push(renderEmptyDepartureCell());
  }
  return cells.join("");
}

function renderBoardNotice(notice) {
  return `<div class="direction-notice board-notice"><span aria-hidden="true">!</span><div>${escapeHtml(notice)}</div></div>`;
}

function renderColumnNotice(notice) {
  return `<div class="direction-notice column-notice"><span aria-hidden="true">!</span><div>${escapeHtml(notice)}</div></div>`;
}

function renderEmptyDepartureCell() {
  return '<div class="departure compact is-empty" aria-hidden="true"><div></div><div></div><div></div></div>';
}

function renderCompactDeparture(row) {
  return `
    <div class="departure compact">
      <div class="route">${escapeHtml(shortLine(row.line))}</div>
      <div class="dest">${escapeHtml(row.destination || "Destination unavailable")}</div>
      <div class="due">${renderDue(row)}</div>
    </div>
  `;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function shortLine(line) {
  const text = String(line || "");
  const match = text.match(/^([TLM]\d+)/i);
  if (match) return match[1].toUpperCase();
  const normalized = text.toLowerCase();
  const longLineMap = [
    [/south coast/, "SCL"],
    [/blue mountains/, "BMT"],
    [/central coast|newcastle/, "CCN"],
    [/southern highlands/, "SHL"],
    [/hunter/, "HUN"],
    [/regional|nsw trainlink/, "NSW"],
  ];
  const mapped = longLineMap.find(([pattern]) => pattern.test(normalized));
  return mapped ? mapped[1] : (line || "--");
}

function renderDeparture(row, mode) {
  const platform = mode === "train" && row.platform ? `<div class="platform">P ${escapeHtml(row.platform)}</div>` : "";
  return `
    <div class="departure">
      <div>
        <div class="route">${escapeHtml(row.line || "--")}</div>
        ${platform}
      </div>
      <div class="dest">${escapeHtml(row.destination || "Destination unavailable")}</div>
      <div class="due">${renderDue(row)}</div>
    </div>
  `;
}

function cssPixelVar(name, fallback) {
  const value = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name));
  return Number.isFinite(value) && value > 0 ? value : fallback;
}

function viewportSize() {
  const viewport = window.visualViewport;
  return {
    width: viewport && viewport.width ? viewport.width : window.innerWidth,
    height: viewport && viewport.height ? viewport.height : window.innerHeight,
  };
}

function isFlowMobileDashboard() {
  return window.matchMedia("(max-width: 639px)").matches;
}

function fitDashboard() {
  const root = document.documentElement;
  if (isFlowMobileDashboard()) {
    root.style.setProperty("--dashboard-scale", "1");
    root.style.setProperty("--dashboard-fit-width", "100%");
    root.style.setProperty("--dashboard-fit-height", "auto");
    return;
  }
  const rootStyle = getComputedStyle(root);
  const baseWidth = cssPixelVar("--dashboard-base-width", window.innerWidth || 1);
  const baseHeight = cssPixelVar("--dashboard-base-height", window.innerHeight || 1);
  const scaleMode = rootStyle.getPropertyValue("--dashboard-scale-mode").trim();
  const available = viewportSize();
  const widthScale = available.width / baseWidth;
  const heightScale = available.height / baseHeight;
  const scale = Math.max(0.1, scaleMode === "width" ? widthScale : Math.min(widthScale, heightScale));
  root.style.setProperty("--dashboard-scale", String(scale));
  root.style.setProperty("--dashboard-fit-width", `${baseWidth * scale}px`);
  root.style.setProperty("--dashboard-fit-height", `${baseHeight * scale}px`);
}

function scheduleDashboardFit() {
  if (resizeTimer) clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    fitDashboard();
    const nextDirectionalRowCount = directionalRowCount();
    const nextTrainSecondaryRowCount = trainSecondaryRowCount();
    if (
      lastTransport
      && (
        nextDirectionalRowCount !== renderedDirectionalRowCount
        || nextTrainSecondaryRowCount !== renderedTrainSecondaryRowCount
      )
    ) {
      renderStops(lastTransport);
      return;
    }
    syncStopTickers();
  }, 80);
}

async function load() {
  try {
    const response = await fetch(`/api/state?t=${Date.now()}`, { cache: "no-store" });
    const data = await response.json();
    els.clock.textContent = data.time || "--:--";
    els.date.textContent = data.date || "---";
    renderWeather(data.weather);
    renderStops(data.transport);
    fitDashboard();
  } catch (error) {
    els.date.textContent = "Update failed";
    fitDashboard();
  }
}

fitDashboard();
window.addEventListener("resize", scheduleDashboardFit);
if (window.visualViewport) {
  window.visualViewport.addEventListener("resize", () => {
    if (!isFlowMobileDashboard()) scheduleDashboardFit();
  });
}

if (!new URLSearchParams(window.location.search).has("skeleton")) {
  load();
  setInterval(load, 60 * 1000);
}
