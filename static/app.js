let state = null;
let route = "/login";
let pageSize = 10;
let pages = {};
let query = { assignments: "", grades: "", courses: "", contents: "" };
let openFolders = { todo: true, now:true, upcoming:true, overdue:true, archived:false, submitted: false, graded: true, pending: true };
let hideEvents = false;
let busy = false;
let feedback = null;
let viewer = null;
let calendarMode = "list";
let calendarDays = 7;
let calendarDay = "";
let calendarReturn = null;
let calendarAnchor = startOfDay(new Date());
let contentsMode = "tree";
let contentsPath = [];
let contentsExpanded = new Set();
let contentsSelected = new Set();
let contentsFolders = new Set();
let contentsAnchor = "";
let contentsSort = { key: "name", dir: 1 };
let contentsOnlySelected = false;
let contentsSearchHere = false;
let contentsDrag = null;
let loading = null;
let colorDialog = null;
let jobError = "";
const SWATCHES = [
  "#9f1239", "#ea580c", "#eab308", "#22c55e", "#2563eb", "#1d4ed8",
  "#15803d", "#a16207", "#c2410c", "#7e22ce", "#0f766e", "#be185d",
  "#4338ca", "#6d28d9", "#db2777", "#0891b2", "#65a30d", "#0f172a",
];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const pendingApi = new Map();
let apiSeq = 0;
let contentsNote = "";
let selectMode = false;
let selectedAssignments = new Set();
let filterDialog = null;
let contentIndex = null;
let searchTimer = 0;
let lazyRequests = new Set();
let courseFilterCache = null;
let manualMarks = new Set();
let detailReturn = "";
const UI_FONTS = {
  segoe: '"Segoe UI", sans-serif',
  calibri: "Calibri, sans-serif",
  candara: "Candara, sans-serif",
  constantia: "Constantia, serif",
  cambria: "Cambria, serif",
  georgia: "Georgia, serif",
  verdana: "Verdana, sans-serif",
  trebuchet: '"Trebuchet MS", sans-serif',
  arial: "Arial, sans-serif",
};
const UI_FONT_LABELS = [
  ["segoe", "Segoe UI"],
  ["calibri", "Calibri"],
  ["candara", "Candara"],
  ["constantia", "Constantia"],
  ["cambria", "Cambria"],
  ["georgia", "Georgia"],
  ["verdana", "Verdana"],
  ["trebuchet", "Trebuchet MS"],
  ["arial", "Arial"],
];
const PAGE_OPENERS = [
  ["system", "System default browser"],
  ["builtin", "Built-in display"],
  ["edge", "Microsoft Edge"],
  ["chrome", "Google Chrome"],
];

function api(path, body) {
  if (!window.chrome || !window.chrome.webview) {
    return Promise.reject(new Error("Open WhiteBoard from its desktop window."));
  }
  const id = ++apiSeq;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pendingApi.delete(id); reject(new Error("The action timed out. Try again.")); }, path === "/api/download" ? 30 * 60 * 1000 : 45000);
    pendingApi.set(id, { resolve, reject, timer });
    window.chrome.webview.postMessage(JSON.stringify({ id, path, body: body || {} }));
  });
}

if (window.chrome && window.chrome.webview) {
  window.chrome.webview.addEventListener("message", (event) => {
    let message = event.data;
    if (typeof message === "string") {
      try { message = JSON.parse(message); } catch (error) { return; }
    }
    if (message && message.event === "download") {
      showDownloadProgress(message);
      return;
    }
    if (!message || message.id == null) return;
    const waiter = pendingApi.get(message.id);
    if (!waiter) return;
    clearTimeout(waiter.timer);
    pendingApi.delete(message.id);
    if (message.error) waiter.reject(new Error(message.error));
    else waiter.resolve(message.body);
  });
}
const NAV = [
  ["/home", "Home", "home"],
  ["/assignments", "Assignments", "assignment"],
  ["/ignored", "Ignored", "hidden"],
  ["/grades", "Grades", "grade"],
  ["/contents", "Contents", "folder"],
  ["/calendar", "Calendar", "calendar"],
  ["/settings", "Settings", "settings"],
];

async function loadState() {
  state = await api("/api/state");
  pageSize = state.page_size || 10;
  hideEvents = !!state.hide_calendar_events;
  contentsMode = state.contents_view_mode || contentsMode;
  if (state.job && state.job.error) jobError = state.job.error;
  if (!state.has_snapshot && route !== "/login") route = "/login";
  contentIndex = null;
  courseFilterCache = null;
  manualMarks = new Set((state.assignments || []).filter((item) => item.manual).map((item) => item.id));
  reapplyManualMarks();
}

async function boot() {
  bindOnce();
  setInterval(tickCountdowns, 1000);
  try { await loadState(); } catch (error) {
    state = { has_snapshot: false };
    jobError = error.message;
  }
  route = state.has_snapshot ? "/home" : "/login";
  window.addEventListener("hashchange", () => {
    route = location.hash.slice(1) || "/login";
    if (route === "/submitted") route = "/assignments";
    if (!state.has_snapshot && route !== "/login") route = "/login";
    render();
  });
  if (location.hash !== "#" + route) location.hash = route;
  else render();
}

function go(path) {
  if (topOf(route) === "/calendar" && String(path).startsWith("/assignments/")) {
    detailReturn = "/calendar";
  } else if (!String(path).startsWith("/assignments/")) {
    detailReturn = "";
  }
  location.hash = path;
}

function applyUiFont(id) {
  document.body.style.fontFamily = UI_FONTS[id] || UI_FONTS.segoe;
}

const RIPPLE_HOST = ".assign, .card, .nav-btn, .outline-btn, .fill-btn, .text-btn, .course-link, .chip-btn, .event-chip, .folder > button";
let pointer = null;
let rippleHost = null;
let rippleFrame = 0;
let pollGen = 0;

function bindOnce() {
  document.addEventListener("pointermove", rememberPointer, true);
  document.addEventListener("pointerover", rememberPointer, true);
  document.addEventListener("pointerenter", onRipple, true);
  document.addEventListener("scroll", onScrollRipple, true);
  document.addEventListener("click", onClick);
  document.addEventListener("pointerdown", onContentsPointerDown);
  document.addEventListener("pointermove", onContentsPointerMove);
  document.addEventListener("pointerup", onContentsPointerUp);
  document.addEventListener("input", onInput);
  document.addEventListener("change", onChange);
  document.addEventListener("submit", onSubmit);
}

function rememberPointer(event) {
  pointer = { x: event.clientX, y: event.clientY };
}

function hostUnderPointer() {
  if (!pointer) return null;
  const node = document.elementFromPoint(pointer.x, pointer.y);
  if (!node || !node.closest) return null;
  return node.closest(RIPPLE_HOST);
}

function spawnRipple(host, x, y) {
  const rect = host.getBoundingClientRect();
  const size = Math.max(rect.width, rect.height) * 1.4;
  const ink = document.createElement("span");
  ink.className = "ripple";
  ink.style.pointerEvents = "none";
  ink.style.width = `${size}px`;
  ink.style.height = `${size}px`;
  ink.style.left = `${x - rect.left - size / 2}px`;
  ink.style.top = `${y - rect.top - size / 2}px`;
  host.appendChild(ink);
  setTimeout(() => ink.remove(), 700);
}

function onRipple(event) {
  const target = event.target;
  if (!target || !target.closest) return;
  const host = target.closest(RIPPLE_HOST);
  if (!host || host === rippleHost) return;
  if (event.relatedTarget && event.relatedTarget.closest && host.contains(event.relatedTarget)) return;
  rippleHost = host;
  spawnRipple(host, event.clientX, event.clientY);
}

function onScrollRipple() {
  if (rippleFrame) return;
  rippleFrame = requestAnimationFrame(() => {
    rippleFrame = 0;
    const host = hostUnderPointer();
    if (host === rippleHost) return;
    rippleHost = host;
    if (host && pointer) spawnRipple(host, pointer.x, pointer.y);
  });
}

function controlOf(event) {
  const target = event.target;
  return target && target.closest ? target : null;
}

function onClick(event) {
  const source = controlOf(event);
  const moreDay = source.closest("[data-cal-day]");
  if (moreDay) { calendarReturn = {mode:calendarMode,anchor:calendarAnchor,scroll:document.getElementById("page-body").scrollTop}; calendarDay=moreDay.dataset.calDay; paintCalendarRoot(); return; }
  if (source.closest("#cal-day-back")) { calendarDay=""; calendarMode=calendarReturn.mode; calendarAnchor=calendarReturn.anchor; paintCalendarRoot(); document.getElementById("page-body").scrollTop=calendarReturn.scroll; return; }
  if (source.closest("#cancel-download")) { api("/api/download/cancel",{}).catch(showError); return; }
  if (source.closest("#school-signin")) { startLogin(true); return; }
  if (source.closest("#show-password")) {
    const input = document.getElementById("pass");
    input.type = input.type === "password" ? "text" : "password";
    source.textContent = input.type === "password" ? "Show password" : "Hide password";
    return;
  }
  if (!source) return;
  const assignCheck = source.closest("[data-assign-select]");
  if (assignCheck) {
    const input = assignCheck.matches("input") ? assignCheck : assignCheck.querySelector("input");
    if (input) {
      if (input.checked) selectedAssignments.add(input.dataset.assignSelect);
      else selectedAssignments.delete(input.dataset.assignSelect);
      refreshAssignToolbar();
    }
    return;
  }
  const assignAction = source.closest("[data-assign-mark], [data-assign-undo], [data-assign-ignore], [data-assign-restore]");
  if (assignAction) {
    const action = assignAction.dataset.assignMark != null ? "submitted"
      : assignAction.dataset.assignUndo != null ? "unsubmit"
      : assignAction.dataset.assignIgnore != null ? "ignore"
      : "restore";
    const id = assignAction.dataset.assignMark || assignAction.dataset.assignUndo
      || assignAction.dataset.assignIgnore || assignAction.dataset.assignRestore;
    changeAssignments(action, [id]);
    return;
  }
  if (source.closest("#assign-select")) {
    selectMode = !selectMode;
    if (!selectMode) selectedAssignments.clear();
    paintPage();
    return;
  }
  if (source.closest("#assign-select-all")) {
    selectMode = true;
    assignmentItems(assignmentMode()).forEach((item) => selectedAssignments.add(item.id));
    paintPage();
    return;
  }
  if (source.closest("#assign-mark")) {
    const ids = assignmentItems(assignmentMode())
      .filter((item) => selectedAssignments.has(item.id) && item.status !== "submitted")
      .map((item) => item.id);
    changeAssignments("submitted", ids);
    return;
  }
  if (source.closest("#assign-ignore")) {
    changeAssignments("ignore", [...selectedAssignments]);
    return;
  }
  if (source.closest("#assign-restore")) {
    changeAssignments("restore", [...selectedAssignments]);
    return;
  }
  if (source.closest("#assign-undo-open") || source.closest("#cal-undo-open")) {
    changeAssignments("undo_not_due", []);
    return;
  }
  if (source.closest("#assign-mark-late")) {
    const count = lateAssignments().length;
    if (!count) return;
    filterDialog = { kind: "late", count };
    paintFilterDialog();
    return;
  }
  if (source.closest("#mark-late-confirm")) {
    const ids = lateAssignments().map((item) => item.id);
    filterDialog = null;
    paintFilterDialog();
    changeAssignments("submitted", ids);
    return;
  }
  const goBtn = source.closest("[data-go]");
  if (goBtn) {
    const nested = source.closest("button, input, a, select, label");
    if (!nested || nested === goBtn) {
      go(goBtn.getAttribute("data-go"));
      return;
    }
  }
  const openBtn = source.closest("[data-open]");
  if (openBtn) {
    openUrl(openBtn.dataset.open, openBtn.dataset.title || "", openBtn.dataset.id || "");
    return;
  }
  const folderBtn = source.closest("[data-folder]");
  if (folderBtn) {
    const key = folderBtn.dataset.folder;
    openFolders[key] = !openFolders[key];
    paintListRoot();
    return;
  }
  const pageBtn = source.closest("[data-page]");
  if (pageBtn) {
    const [key, delta] = pageBtn.dataset.page.split(":");
    pages[key] = Math.max(0, (pages[key] || 0) + Number(delta));
    if (topOf(route) === "/calendar") paintCalendarRoot();
    else if (route === "/contents") paintContentsRoot();
    else paintListRoot();
    return;
  }
  const feedbackBtn = source.closest("[data-feedback]");
  if (feedbackBtn) {
    event.stopPropagation();
    feedback = [...state.graded, ...state.pending].find((item) => item.id === feedbackBtn.dataset.feedback) || null;
    paintPage();
    return;
  }
  if (source.closest("#close-feedback")) {
    feedback = null;
    paintPage();
    return;
  }
  if (source.closest("#filter-new")) {
    filterDialog = { kind: "new", name: "", selected: new Set(), error: "" };
    paintFilterDialog();
    return;
  }
  const filterToggle = source.closest("[data-filter-toggle]");
  if (filterToggle) {
    const id = filterToggle.dataset.filterToggle;
    const current = state.active_custom_filter || "";
    saveFilters({ active_custom_filter: current === id ? "" : id });
    return;
  }
  const filterDelete = source.closest("[data-filter-delete]");
  if (filterDelete) {
    const id = filterDelete.dataset.filterDelete;
    const item = (state.custom_filters || []).find((row) => row.id === id);
    filterDialog = { kind: "delete", id, name: item ? item.name : "this filter" };
    paintFilterDialog();
    return;
  }
  if (source.closest("#filter-cancel")) {
    filterDialog = null;
    paintFilterDialog();
    return;
  }
  if (source.closest("#filter-save")) {
    saveNewFilter();
    return;
  }
  if (source.closest("#filter-delete-confirm") && filterDialog) {
    const id = filterDialog.id;
    filterDialog = null;
    saveFilters({ delete_custom_filter: id });
    return;
  }
  const reveal = source.closest("[data-reveal]");
  if (reveal) {
    revealContent(reveal.dataset.reveal);
    return;
  }
  if (source.closest("#refresh")) {
    refreshNow();
    return;
  }
  if (source.closest("#logout")) {
    signOut();
    return;
  }
  if (source.closest("#saved")) {
    go("/home");
    return;
  }
  if (source.closest("#sign-in")) {
    startLogin();
    return;
  }
  if (source.closest("#viewer-home") || source.closest("#viewer-back")) {
    viewer = null;
    render();
    return;
  }
  const calMode = source.closest("[data-cal-mode]");
  if (calMode) {
    calendarMode = calMode.dataset.calMode;
    pages["calendar-list"] = 0;
    paintPage();
    return;
  }
  if (source.closest("#cal-today")) {
    calendarAnchor = startOfDay(new Date());
    paintPage();
    return;
  }
  if (source.closest("#cal-prev")) {
    shiftCalendar(-1);
    paintPage();
    return;
  }
  if (source.closest("#cal-next")) {
    shiftCalendar(1);
    paintPage();
    return;
  }
  const daysBtn = source.closest("[data-cal-days]");
  if (daysBtn) {
    calendarDays = Number(daysBtn.dataset.calDays);
    pages["calendar-list"] = 0;
    document.querySelectorAll("[data-cal-days]").forEach((button) => {
      button.classList.toggle("active", Number(button.dataset.calDays) === calendarDays);
    });
    const title = document.getElementById("cal-period");
    if (title) title.textContent = periodTitle();
    paintCalendarRoot();
    return;
  }
  if (source.closest("#hide-events")) {
    hideEvents = !hideEvents;
    source.closest("#hide-events").classList.toggle("active", hideEvents);
    persistSettings({ hide_calendar_events: hideEvents });
    paintCalendarRoot();
    return;
  }
  const contentsModeBtn = source.closest("[data-contents-mode]");
  if (contentsModeBtn) {
    contentsMode = contentsModeBtn.dataset.contentsMode;
    persistSettings({ contents_view_mode: contentsMode });
    paintPage();
    return;
  }
  const expandBtn = source.closest("[data-expand]");
  if (expandBtn) {
    const key = expandBtn.dataset.expand;
    if (contentsExpanded.has(key)) contentsExpanded.delete(key);
    else contentsExpanded.add(key);
    paintContentsRoot();
    return;
  }
  const contentsOpen = source.closest("[data-contents-open]");
  if (contentsOpen) {
    contentsOpenFolder(contentsOpen.dataset.contentsParent || null, contentsOpen.dataset.contentsOpen);
    paintPage();
    return;
  }
  if ((source.closest("[id]") || source).id === "contents-up") {
    contentsPath = contentsPath.slice(0, -1);
    paintPage();
    return;
  }
  const crumb = source.closest("[data-crumb]");
  if (crumb) {
    const index = Number(crumb.dataset.crumb);
    contentsPath = index < 0 ? [] : contentsPath.slice(0, index + 1);
    paintPage();
    return;
  }
  const sortBtn = source.closest("[data-sort]");
  if (sortBtn) {
    const key = sortBtn.dataset.sort;
    if (contentsSort.key === key) contentsSort.dir = -contentsSort.dir;
    else contentsSort = { key, dir: 1 };
    paintContentsRoot();
    return;
  }
  if (source.closest("#contents-view-selected")) {
    contentsOnlySelected = !contentsOnlySelected;
    paintPage();
    return;
  }
  if (source.closest("#contents-search-here")) {
    contentsSearchHere = !contentsSearchHere;
    pages["contents-search"] = 0;
    paintContentsRoot();
    return;
  }
  const selectBtn = source.closest("[data-select]");
  if (selectBtn) {
    const box = selectBtn.querySelector("input[type=checkbox]");
    if (!box) return;
    const apply = () => {
      const id = selectBtn.dataset.select;
      if (source.shiftKey && contentsAnchor) return;
      toggleContentSelected(id, box.checked);
      contentsAnchor = id;
      refreshContentsSelection();
    };
    if (source.matches("input[type=checkbox]")) apply();
    else setTimeout(apply, 0);
    return;
  }
  if (source.closest("#contents-download")) {
    downloadSelected();
    return;
  }
  if ((source.closest("[id]") || source).id === "contents-open-selected") {
    const node = (state.content_nodes || []).find((item) => contentsSelected.has(item.id) && item.url);
    if (node) openUrl(node.url);
    return;
  }
  if ((source.closest("[id]") || source).id === "google-signin") {
    googleAction("/api/google/signin");
    return;
  }
  if ((source.closest("[id]") || source).id === "google-sync") {
    googleAction("/api/google/sync");
    return;
  }
  if ((source.closest("[id]") || source).id === "google-signout") {
    googleAction("/api/google/signout");
    return;
  }
  if (source.closest("#cancel-loading")) {
    api("/api/cancel", { id: (loading || {}).id }).catch(showError);
    if (loading) loading.message = "Cancelling…";
    render();
    return;
  }
  const deadlineColor = source.closest("[data-deadline-color]");
  if (deadlineColor) {
    openColorDialog(
      `${deadlineColor.dataset.deadlineLabel} color`,
      deadlineColor.dataset.deadlineCurrent,
      (color) => persistSettings({ deadline_color: { key: deadlineColor.dataset.deadlineColor, color } }).then(() => { colorDialog = null; render(); })
    );
    return;
  }
  const courseColor = source.closest("[data-course-color]");
  if (courseColor) {
    openColorDialog(
      courseColor.dataset.courseName,
      courseColor.dataset.courseCurrent,
      (color) => persistSettings({ course_color: { id: courseColor.dataset.courseColor, color } }).then(() => { colorDialog = null; render(); })
    );
    return;
  }
  if ((source.closest("[id]") || source).id === "reset-deadline-colors") {
    persistSettings({ reset_deadline_colors: true }).then(() => render());
    return;
  }
  if ((source.closest("[id]") || source).id === "reset-course-colors") {
    persistSettings({ reset_course_colors: true }).then(() => render());
    return;
  }
  const resetCourse = source.closest("[data-reset-course]");
  if (resetCourse) {
    persistSettings({ reset_course_color: resetCourse.dataset.resetCourse }).then(() => render());
    return;
  }
  const swatch = source.closest("[data-swatch]");
  if (swatch && colorDialog) {
    colorDialog.current = swatch.dataset.swatch;
    const field = document.getElementById("color-hex");
    if (field) field.value = colorDialog.current;
    return;
  }
  if ((source.closest("[id]") || source).id === "color-cancel") {
    colorDialog = null;
    paintPage();
    return;
  }
  if ((source.closest("[id]") || source).id === "color-apply" && colorDialog) {
    const field = document.getElementById("color-hex");
    const value = (field && field.value) || colorDialog.current;
    if (!/^#?[0-9a-fA-F]{6}$/.test(value.trim())) return;
    const hex = value.trim().startsWith("#") ? value.trim() : `#${value.trim()}`;
    const apply = colorDialog.onPick;
    colorDialog = null;
    apply(hex.toLowerCase());
  }
}

function onInput(event) {
  if (event.target.id === "course-q") {
    query.courses = event.target.value;
    paintCourses();
    if (route === "/contents" || route === "/grades") paintPage();
    return;
  }
  if (event.target.id === "contents-search") {
    query.contents = event.target.value;
    pages["contents-search"] = 0;
    clearTimeout(searchTimer); searchTimer = setTimeout(paintContentsRoot, 120);
    return;
  }
  if (event.target.id === "filter-name" && filterDialog) {
    filterDialog.name = event.target.value;
  }
  if (event.target.id === "list-search") {
    const key = event.target.dataset.key;
    query[key] = event.target.value;
    pages[key] = 0;
    paintListRoot();
    return;
  }
}

function onChange(event) {
  if (event.target.id === "history-mode") {
    const mode = event.target.value;
    saveFilters({
      assignment_history: mode,
      assignment_history_date: state.assignment_history_date || "",
    });
    return;
  }
  if (event.target.id === "history-date") {
    saveFilters({ assignment_history: "date", assignment_history_date: event.target.value });
    return;
  }
  if (event.target.id === "course-activity") {
    saveFilters({ inactivity: event.target.value });
    return;
  }
  if (event.target.id === "hide-filtered") {
    saveFilters({ hide_filtered_assignments: event.target.checked });
    return;
  }
  if (event.target.id === "ui-font") {
    if (state) state.ui_font = event.target.value;
    applyUiFont(event.target.value);
    persistSettings({ ui_font: event.target.value });
    return;
  }
  if (event.target.id === "page-opener") {
    if (state) state.page_opener = event.target.value;
    persistSettings({ page_opener: event.target.value });
    return;
  }
  if (event.target.id === "load-filter") {
    saveFilters({ load_filter_courses_only: event.target.checked });
    return;
  }
  if (event.target.matches("[data-filter-course]") && filterDialog) {
    const id = event.target.dataset.filterCourse;
    if (event.target.checked) filterDialog.selected.add(id);
    else filterDialog.selected.delete(id);
    return;
  }
  if (event.target.id === "page-size") {
    pageSize = Number(event.target.value);
    pages = {};
    persistSettings({ list_page_size: pageSize });
    paintPage();
    return;
  }
  if (event.target.id === "google-sync-enabled") {
    persistSettings({ google_sync_enabled: event.target.checked });
  }
}

function beginLoading(kind, message) {
  pollGen += 1;
  loading = {
    kind,
    percent: 0.02,
    message,
    detail: "",
    log: [],
    counts: { courses: 0, folders: 0, files: 0 },
  };
  document.title = `WhiteBoard — ${message}`;
  render();
}

function startLogin(interactive = false) {
  const username = (document.getElementById("user") || {}).value || "";
  const password = (document.getElementById("pass") || {}).value || "";
  const baseUrl = (document.getElementById("base-url") || {}).value || "";
  try { const url = new URL(baseUrl); if (url.protocol !== "https:" || url.username || url.password || !username.trim() || (!interactive && !password)) throw new Error(); }
  catch (_) { jobError = "Enter an HTTPS school address, username, and password (or choose school sign-in)."; render(); return; }
  beginLoading("login", "Signing in…");
  api("/api/login", { username: username.trim(), password, base_url: baseUrl.trim(), interactive })
    .then(() => pollJob()).catch(error => { loading = null; busy = false; showError(error); });
}

function onSubmit(event) {
  if (event.target.id !== "login-form") return;
  event.preventDefault();
  startLogin();
}

async function pollJob() {
  const mine = ++pollGen;
  let failures = 0;
  let shownRevision = 0;
  while (mine === pollGen) {
    let job = null;
    try {
      job = await api("/api/progress");
      if (mine !== pollGen) return;
    } catch (error) {
      if (mine !== pollGen) return;
      if (++failures >= 3) { loading = null; busy = false; showError(error); return; }
      loading = {
        kind: (loading && loading.kind) || "login",
        percent: loading ? loading.percent : 0,
        message: (error && error.message) || "Could not read sign-in progress.",
      };
      render();
      await new Promise((resolve) => setTimeout(resolve, 700));
      continue;
    }
    failures = 0;
    loading = {
      id: job.id,
      kind: job.kind || (loading && loading.kind) || "refresh",
      percent: job.percent || 0,
      message: job.message || "Working…",
      detail: job.detail || "",
      log: job.log || [],
      counts: job.counts || null,
    };
    const changedStage = job.revision > shownRevision;
    if (changedStage) {
      shownRevision = job.revision; await loadState();
      if (state.has_snapshot && route === "/login") { route = "/home"; location.hash = route; }
    }
    document.title = `WhiteBoard — ${loading.message}`;
    if (state.has_snapshot && document.getElementById("shell") && !changedStage) paintChrome(); else render();
    if (!job.busy) {
      await loadState();
      loading = null;
      busy = false;
      if (job.error) {
        jobError = job.error;
        if (!state.has_snapshot) route = "/login";
      } else {
        jobError = "";
        if (state.has_snapshot && (route === "/login" || !route)) {
          route = "/home";
          if (location.hash !== "#/home") location.hash = "/home";
        }
      }
      render();
      const note = document.getElementById("login-note");
      if (note && job.error) note.textContent = job.error;
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
}

async function persistSettings(body) {
  const result = await api("/api/settings", body);
  if (result && Array.isArray(result.courses)) {
    const kept = new Set(manualMarks);
    (result.assignments || []).forEach((item) => {
      if (item.manual) kept.add(item.id);
    });
    manualMarks = kept;
    state = result;
    reapplyManualMarks();
    contentIndex = null;
    courseFilterCache = null;
    pageSize = state.page_size || pageSize;
    hideEvents = !!state.hide_calendar_events;
    return state;
  }
  if (result && result.patch) {
    Object.assign(state, result.patch);
    courseFilterCache = null;
    reapplyManualMarks();
    if (result.patch.page_size) pageSize = result.patch.page_size;
    if ("hide_calendar_events" in result.patch) hideEvents = !!result.patch.hide_calendar_events;
    if ("google_sync_enabled" in result.patch && state.google) {
      state.google.sync_enabled = !!result.patch.google_sync_enabled;
    }
  }
  return state;
}

function reapplyManualMarks() {
  if (!state || !manualMarks.size) return;
  const flag = (item) => {
    if (!item) return;
    if (!manualMarks.has(item.id) && !manualMarks.has(item.assignment_id)) return;
    item.manual = true;
    item.status = "submitted";
    item.finished = true;
  };
  (state.assignments || []).forEach(flag);
  (state.calendar || []).forEach(flag);
  (state.home_due || []).forEach(flag);
  Object.values(state.course_pages || {}).forEach((page) => {
    (page.upcoming || []).forEach(flag);
  });
}

async function googleAction(path) {
  busy = true;
  paintChrome();
  state = await api(path, {});
  pollGoogle();
}

async function pollGoogle() {
  try { Object.assign(state, await api("/api/google/status")); } catch (error) { busy=false; showError(error); return; }
  if (route === "/settings") paintPage();
  paintChrome();
  if (state.google_busy) {
    setTimeout(pollGoogle, 800);
    return;
  }
  busy = false;
  paintChrome();
}

async function refreshNow() {
  busy = true;
  beginLoading("refresh", "Refreshing from Blackboard…");
  api("/api/refresh", {}).then(() => pollJob()).catch(error => { loading = null; busy = false; showError(error); });
}

function render() {
  applyUiFont(state && state.ui_font);
  const app = document.getElementById("app");
  if (loading && !(state && state.has_snapshot)) {
    app.innerHTML = loadingView();
    return;
  }
  if (!state || route === "/login" || !state.has_snapshot) {
    app.innerHTML = loginView();
    return;
  }
  if (viewer) {
    app.innerHTML = viewerView();
    return;
  }
  if (!document.getElementById("shell")) {
    app.innerHTML = shellFrame();
  }
  paintChrome();
  paintFilterChrome();
  paintCourses();
  paintFilterDialog();
  paintPage();
  tickCountdowns();
}

function loadingView() {
  const percent = Math.max(0, Math.min(100, Math.round((loading.percent || 0) * 100)));
  const title = loading.percent > .12 ? "Loading your dashboard" : "Signing in";
  const blurb = loading.message || (loading.kind === "refresh"
    ? "Collecting courses, assignment links, and submission status."
    : "Opening Blackboard…");
  const counts = loading.counts || {};
  const countLine = (counts.courses || counts.folders || counts.files)
    ? `${counts.courses || 0} courses · ${counts.folders || 0} folders · ${counts.files || 0} files`
    : "";
  const latest = loading.detail
    ? `<p class="load-latest"><span class="muted">Latest</span><br>${escapeHtml(loading.detail)}</p>`
    : "";
  const log = (loading.log || []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");
  return `<div class="loading-screen"><div class="loading-card">
    <div class="row" style="justify-content:center"><img src="logo.png" width="64" height="64" alt="" /></div>
    <h2>${title}</h2>
    <p>${escapeHtml(blurb)}</p>
    <div class="row"><span class="muted">Progress</span><span class="spacer"></span><span class="muted">${percent}%</span></div>
    <div class="load-track"><span style="width:${Math.max(percent, 4)}%"></span></div>
    ${countLine ? `<p class="load-counts">${escapeHtml(countLine)}</p>` : ""}
    ${latest}
    ${log ? `<ul class="load-log">${log}</ul>` : ""}
    <button class="text-btn" id="cancel-loading" style="margin-top:16px">Cancel</button>
  </div></div>`;
}

function loginView() {
  const saved = state && state.has_snapshot
    ? '<button class="outline-btn" type="button" id="saved">Open saved dashboard</button>'
    : "";
  return `<div class="login"><form class="card" id="login-form">
    <div class="row"><img src="logo.png" width="48" height="48" alt="" /><h2>WhiteBoard</h2></div>
    <p class="muted">See your deadlines, grades, and course files together. Your password is sent only to your school and is never saved. For SSO or MFA, choose school sign-in.</p>
    <label for="base-url">School URL</label><input type="url" autocomplete="url" required id="base-url" value="${escapeAttr((state && state.base_url) || "https://shs.blackboardchina.cn")}" />
    <label for="user">Username</label><input type="text" autocomplete="username" required id="user" value="${escapeAttr((state && state.username) || "")}" />
    <label for="pass">Password</label><input type="password" autocomplete="current-password" id="pass" /><button class="text-btn" id="show-password" type="button">Show password</button>
    <div class="row" style="margin-top:14px">
      <button class="fill-btn" id="sign-in" type="button">Sign in</button>
      <button class="outline-btn" id="school-signin" type="button">School sign-in (SSO / MFA)</button>
      ${saved}
    </div>
    <p class="muted" id="login-note">${escapeHtml(jobError || "")}</p>
  </form></div>`;
}

function shellFrame() {
  return `<div class="app" id="shell">
    <aside class="sidebar">
      <div class="brand"><img src="logo.png" alt="" /><span>WhiteBoard</span></div>
      <div class="label">Your courses</div>
      <input id="course-q" placeholder="Search courses" value="${escapeAttr(query.courses)}" />
      <label class="side-note" for="course-activity">Activity</label>
      <select id="course-activity">
        ${activityOptions()}
      </select>
      <div class="filter-head"><span>Custom filters</span><button id="filter-new" type="button">New</button></div>
      <div class="filter-chips" id="filter-chips"></div>
      <label class="check"><input id="hide-filtered" type="checkbox" /> Hide assignments outside this filter</label>
      <label class="check"><input id="load-filter" type="checkbox" /> Next launch, only load this filter</label>
      <div class="course-list" id="course-list"></div>
      <div id="filter-modal"></div>
    </aside>
    <div class="main">
      <header class="topbar" id="topbar"></header>
      <div id="busy-slot"></div>
      <div class="content" id="page-body"></div>
    </div>
  </div>`;
}

function paintChrome() {
  const topbar = document.getElementById("topbar");
  const busySlot = document.getElementById("busy-slot");
  if (!topbar) return;
  const nav = NAV.map(([path, label, icon]) => {
    const active = topOf(route) === path ? "active" : "";
    const badge = path === "/assignments" ? todoBadge() : "";
    return `<button class="nav-btn ${active}" data-go="${path}">${navIcon(icon)}<span class="label">${label}</span>${badge}</button>`;
  }).join("");
  topbar.innerHTML = `
    <img class="logo" src="logo.png" alt="" />
    ${nav}
    <span class="spacer"></span>
    <span class="muted">${escapeHtml(state.fetched_at)}</span>
    <span class="muted">${escapeHtml(state.user_name || "")}</span>
    ${busy || state.google_busy ? '<span class="spin"></span>' : ""}
    <button class="outline-btn pill" id="refresh">Refresh</button>
    <button class="text-btn pill" id="logout">Log out</button>`;
  if (busySlot) {
    const on = busy || state.google_busy;
    busySlot.innerHTML = loading ? `<div class="sync-status" role="status">${escapeHtml(loading.message)} <button id="cancel-loading" class="text-btn">Cancel refresh</button>${state.partial ? '<span>Some details are still being verified.</span>' : ''}</div>` : `<div class="busy-bar ${on ? "" : "idle"}"><span></span></div>`;
  }
}

const INACTIVITY_DAYS = { "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365 };

function activityOptions() {
  const current = (state && state.inactivity) || "all";
  return [
    ["all", "Any activity"],
    ["1w", "Past 1 week"],
    ["1m", "Past 1 month"],
    ["3m", "Past 3 months"],
    ["6m", "Past 6 months"],
    ["1y", "Past 1 year"],
  ].map(([key, label]) => `<option value="${key}" ${key === current ? "selected" : ""}>${label}</option>`).join("");
}

function activeCustomFilter() {
  const id = (state && state.active_custom_filter) || "";
  return ((state && state.custom_filters) || []).find((item) => item.id === id) || null;
}

function courseFilteredOut(course) {
  const custom = activeCustomFilter();
  if (custom) {
    const allowed = new Set(custom.course_ids || []);
    if (!allowed.has(course.id)) return true;
  }
  const days = INACTIVITY_DAYS[state.inactivity || "all"];
  if (days && course.activity && course.activity < Date.now() / 1000 - days * 86400) return true;
  return false;
}

function visibleCourseIds() {
  const filter = activeCustomFilter();
  const stamp = `${state.inactivity}|${filter ? filter.id : ""}|${(state.courses || []).length}`;
  if (courseFilterCache && courseFilterCache.stamp === stamp) return courseFilterCache.ids;
  const ids = new Set((state.courses || []).filter((course) => !courseFilteredOut(course)).map((course) => course.id));
  courseFilterCache = { stamp, ids };
  return ids;
}

function inActiveFilter(courseId) {
  if (!state.hide_filtered_assignments) return true;
  const allowed = visibleCourseIds();
  if (!allowed.size) return true;
  return allowed.has(courseId);
}

function listedCourses() {
  const needle = query.courses.trim().toLowerCase();
  const rows = [];
  (state.courses || []).forEach((course) => {
    const hidden = courseFilteredOut(course);
    if (needle) {
      const haystack = `${course.name} ${course.term || ""} ${course.instructor || ""}`.toLowerCase();
      if (haystack.includes(needle)) rows.push({ course, hidden });
    } else if (!hidden) {
      rows.push({ course, hidden: false });
    }
  });
  return rows;
}

function shownCourses() {
  return listedCourses()
    .filter((row) => !(row.hidden && state.hide_filtered_assignments))
    .map((row) => row.course);
}

function paintFilterChrome() {
  const chips = document.getElementById("filter-chips");
  if (!chips) return;
  const active = state.active_custom_filter || "";
  const filters = state.custom_filters || [];
  chips.innerHTML = filters.length
    ? filters.map((item) => `<span class="filter-chip ${item.id === active ? "on" : ""}">
        <button class="name" type="button" data-filter-toggle="${escapeAttr(item.id)}">${escapeHtml(item.name)}</button>
        <button class="x" type="button" data-filter-delete="${escapeAttr(item.id)}" aria-label="Delete filter">×</button>
      </span>`).join("")
    : `<p class="side-note">No custom filters yet.</p>`;
  const activity = document.getElementById("course-activity");
  if (activity && document.activeElement !== activity) activity.value = state.inactivity || "all";
  const hide = document.getElementById("hide-filtered");
  if (hide) hide.checked = !!state.hide_filtered_assignments;
  const load = document.getElementById("load-filter");
  if (load) load.checked = !!state.load_filter_courses_only;
}

function paintFilterDialog() {
  const host = document.getElementById("filter-modal");
  if (!host) return;
  host.innerHTML = filterDialog ? filterModal() : "";
}

function filterModal() {
  if (filterDialog.kind === "late") {
    const count = filterDialog.count || 0;
    const noun = count === 1 ? "assignment" : "assignments";
    return `<div class="modal-back"><div class="modal">
      <h3>Mark overdue assignments done in WhiteBoard?</h3>
      <p>This marks ${count} overdue ${noun} done in WhiteBoard only. It does not submit coursework to Blackboard. Undo is available on each card.</p>
      <div class="row" style="margin-top:12px">
        <button class="text-btn" id="filter-cancel" type="button">Cancel</button>
        <button class="fill-btn" id="mark-late-confirm" type="button">Mark done locally</button>
      </div>
    </div></div>`;
  }
  if (filterDialog.kind === "delete") {
    return `<div class="modal-back"><div class="modal">
      <h3>Delete filter?</h3>
      <p>Delete "${escapeHtml(filterDialog.name)}"? This cannot be undone.</p>
      <div class="row" style="margin-top:12px">
        <button class="text-btn" id="filter-cancel" type="button">Cancel</button>
        <button class="fill-btn danger" id="filter-delete-confirm" type="button">Delete</button>
      </div>
    </div></div>`;
  }
  const boxes = (state.courses || []).map((course) => `<label class="check">
      <input type="checkbox" data-filter-course="${escapeAttr(course.id)}" ${filterDialog.selected.has(course.id) ? "checked" : ""} />
      <span>${escapeHtml(course.name)}</span>
    </label>`).join("");
  return `<div class="modal-back"><div class="modal">
    <h3>New course filter</h3>
    <p class="muted">Only the courses you check appear in the left list when this filter is on. Assignments and deadlines from other courses still show until you hide them.</p>
    <label>Filter name</label>
    <input id="filter-name" type="text" value="${escapeAttr(filterDialog.name || "")}" />
    <div class="filter-courses">${boxes || `<p class="muted">Sign in to choose courses.</p>`}</div>
    <p class="warn" id="filter-error">${escapeHtml(filterDialog.error || "")}</p>
    <div class="row">
      <button class="text-btn" id="filter-cancel" type="button">Cancel</button>
      <button class="fill-btn" id="filter-save" type="button">Save</button>
    </div>
  </div></div>`;
}

function saveFilters(body) {
  const local = {};
  ["inactivity", "hide_filtered_assignments", "load_filter_courses_only", "active_custom_filter", "assignment_history", "assignment_history_date"].forEach((key) => {
    if (key in body) local[key] = body[key];
  });
  Object.assign(state, local);
  courseFilterCache = null;
  paintFilterChrome();
  paintCourses();
  paintFilterDialog();
  paintPage();
  updateTodoBadge();
  persistSettings(body).then(() => {
    paintFilterChrome();
    paintCourses();
    paintPage();
    updateTodoBadge();
  }).catch(() => {});
}

function saveNewFilter() {
  const field = document.getElementById("filter-name");
  const name = ((field && field.value) || "").trim();
  const ids = [...(filterDialog ? filterDialog.selected : [])];
  if (!name) {
    filterDialog.error = "Give the filter a name.";
    const note = document.getElementById("filter-error");
    if (note) note.textContent = filterDialog.error;
    return;
  }
  if (!ids.length) {
    filterDialog.error = "Select at least one course for the whitelist.";
    const note = document.getElementById("filter-error");
    if (note) note.textContent = filterDialog.error;
    return;
  }
  filterDialog = null;
  saveFilters({ add_custom_filter: { name, course_ids: ids } });
}

function paintCourses() {
  const box = document.getElementById("course-list");
  if (!box) return;
  const rows = listedCourses();
  const empty = query.courses.trim() ? "No matching courses." : "No courses in this filter.";
  box.innerHTML = rows.map(({ course, hidden }) => {
    const active = route.endsWith(course.id) ? "active" : "";
    const style = hidden
      ? "background:#e2e8f0;border-color:#cbd5e1;opacity:0.55"
      : `background:${course.fill};border-color:${course.ink}`;
    const flag = hidden ? `<span class="flag">Filtered out</span>` : "";
    return `<button class="course-link ${active}" data-go="/courses/${encodeURIComponent(course.id)}" style="${style}">
      <span class="name">${escapeHtml(course.name)}</span>
      <span class="term">${escapeHtml(course.term || "Course")}</span>
      ${flag}
    </button>`;
  }).join("") || `<p class="side-note">${empty}</p>`;
}

function paintPage() {
  const body = document.getElementById("page-body");
  if (!body) return;
  const banner = jobError ? `<div class="banner">${escapeHtml(jobError)}</div>` : "";
  body.innerHTML = banner + viewFor(route);
  animateMeters();
}

function paintListRoot() {
  const root = document.getElementById("list-root");
  if (!root) {
    paintPage();
    return;
  }
  if (route === "/assignments" || route === "/submitted") root.innerHTML = assignmentFolders("all");
  else if (route === "/ignored") root.innerHTML = assignmentFolders("ignored");
  else if (route === "/grades") root.innerHTML = gradesLists();
  else paintPage();
}

function paintCalendarRoot() {
  const root = document.getElementById("calendar-root");
  if (!root) {
    paintPage();
    return;
  }
  root.innerHTML = calendarBody();
}

function paintContentsRoot() {
  const root = document.getElementById("contents-root");
  if (!root) {
    paintPage();
    return;
  }
  root.innerHTML = contentsBody();
}

function viewFor(path) {
  if (path.startsWith("/courses/")) return courseView(decodeURIComponent(path.slice("/courses/".length)));
  if (path.startsWith("/assignments/")) return assignmentView(decodeURIComponent(path.slice("/assignments/".length)));
  if (path === "/assignments" || path === "/submitted") return assignmentList("all");
  if (path === "/ignored") return assignmentList("ignored");
  if (path === "/grades") return gradesView();
  if (path === "/calendar") return calendarView();
  if (path === "/contents") { ensureLazyContent(); return contentsView(); }
  if (path === "/settings") return settingsView();
  return homeView();
}

function homeView() {
  const dueItems = (state.home_due || []).filter((item) =>
    !item.ignored && !item.finished && keptByHistory(item) && (!item.course_id || inActiveFilter(item.course_id))
  );
  const gradeItems = (state.home_grades || []).filter((grade) => inActiveFilter(grade.course_id));
  const due = dueItems.map((item) => assignCard(item, item.kind !== "other")).join("") || `<p class="empty">No deadlines this week.</p>`;
  const grades = gradeItems.map((grade) => `<div class="card row grade-card" data-go="${grade.assignment_id ? "/assignments/" + encodeURIComponent(grade.assignment_id) : "/courses/" + encodeURIComponent(grade.course_id)}" style="background:${grade.fill};border-color:${grade.ink}"><div><strong>${escapeHtml(grade.title)}</strong><div class="muted">${escapeHtml(grade.course)}</div></div><span class="spacer"></span><strong style="color:${grade.ink}">${escapeHtml(grade.label)}</strong></div>`).join("") || `<p class="empty">No new grades.</p>`;
  const banners = errorBanners();
  return `<h2>Home</h2><p class="muted">This week at a glance.</p>${banners}
    <h3>Upcoming this week</h3>${legend()}${due}
    <h3>Recent grades</h3>${grades}`;
}

function assignmentMode() {
  if (route === "/ignored") return "ignored";
  return "all";
}

function todoCount() {
  if (!state || !state.assignments) return 0;
  return state.assignments.filter(item => item.status !== "submitted" && !item.ignored && keptByHistory(item) && inActiveFilter(item.course_id)).length;
}

function todoBadge() {
  const count = todoCount();
  return `<span class="todo-badge" id="todo-badge" ${count ? "" : "hidden"}>${count}</span>`;
}

function updateTodoBadge() {
  const badge = document.getElementById("todo-badge");
  if (!badge) return;
  const count = todoCount();
  badge.textContent = String(count);
  badge.hidden = count === 0;
}

const HISTORY_DAYS = { "1w": 7, "1m": 30, "3m": 90, "6m": 180, "1y": 365 };

function historyCutoff() {
  const mode = (state && state.assignment_history) || "off";
  if (mode === "date") {
    const raw = state.assignment_history_date || "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(raw)) return 0;
    const ts = new Date(`${raw}T00:00:00`).getTime() / 1000;
    return Number.isFinite(ts) ? ts : 0;
  }
  const days = HISTORY_DAYS[mode];
  if (!days) return 0;
  return Date.now() / 1000 - days * 86400;
}

function keptByHistory(item) {
  const cutoff = historyCutoff();
  if (!cutoff) return true;
  const ts = item.ts || 0;
  if (!ts || item.kind === "other") return true;
  return ts >= cutoff;
}

function historyControl() {
  const mode = state.assignment_history || "off";
  const options = [
    ["off", "Show all assignments"],
    ["1w", "Hide due more than 1 week ago"],
    ["1m", "Hide due more than 1 month ago"],
    ["3m", "Hide due more than 3 months ago"],
    ["6m", "Hide due more than 6 months ago"],
    ["1y", "Hide due more than 1 year ago"],
    ["date", "Hide due before a date"],
  ].map(([key, label]) => `<option value="${key}" ${mode === key ? "selected" : ""}>${label}</option>`).join("");
  const date = mode === "date"
    ? `<input id="history-date" type="date" value="${escapeAttr(state.assignment_history_date || "")}" />`
    : "";
  return `<div class="row">
      <label class="muted" for="history-mode">Old assignments</label>
      <select id="history-mode">${options}</select>
      ${date}
    </div>
    <p class="muted">This display filter is reversible. Refresh keeps older assignments available.</p>`;
}

function byDueSoonest(a, b) {
  const left = a.ts || 0;
  const right = b.ts || 0;
  if (!left && !right) return (a.title || "").localeCompare(b.title || "");
  if (!left) return 1;
  if (!right) return -1;
  return left - right || (a.title || "").localeCompare(b.title || "");
}

function assignmentItems(mode) {
  reapplyManualMarks();
  const needle = query.assignments.toLowerCase();
  let items = (state.assignments || []).filter((item) =>
    keptByHistory(item)
    && `${item.title} ${item.course}`.toLowerCase().includes(needle)
    && inActiveFilter(item.course_id)
  );
  if (mode === "ignored") return items.filter((item) => item.ignored).sort(byDueSoonest);
  items = items.filter((item) => !item.ignored);
  if (mode === "submitted") return items.filter((item) => item.status === "submitted").sort(byDueSoonest);
  return items.sort(byDueSoonest);
}

function assignmentList(mode) {
  const title = mode === "submitted" ? "Submitted" : mode === "ignored" ? "Ignored" : "Assignments";
  return `<h2>${title}</h2>${historyControl()}${assignToolbar(mode)}${searchBox("assignments", "Search assignments")}<div id="list-root">${assignmentFolders(mode)}</div>`;
}

function assignToolbar(mode) {
  const items = assignmentItems(mode);
  const selected = items.filter((item) => selectedAssignments.has(item.id));
  const markable = selected.filter((item) => item.status !== "submitted").length;
  const undoOpen = notDueMarked().length;
  const late = mode === "ignored" ? [] : lateAssignments();
  const bulk = mode === "ignored"
    ? `<button class="outline-btn with-icon" id="assign-restore" type="button" ${selected.length ? "" : "disabled"}>${actionIcon("restore")}<span>Restore selected (${selected.length})</span></button>`
    : `<button class="outline-btn with-icon mark-btn" id="assign-mark" type="button" ${markable ? "" : "disabled"}>${actionIcon("submitted")}<span>Mark done (${markable})</span></button>
       <button class="outline-btn with-icon" id="assign-ignore" type="button" ${selected.length ? "" : "disabled"}>${actionIcon("ignore")}<span>Ignore selected (${selected.length})</span></button>`;
  const undoButton = `<button class="outline-btn with-icon" id="assign-undo-open" type="button" title="Clear the submitted mark on every item that is not due yet." ${undoOpen ? "" : "disabled"}>${actionIcon("undo")}<span>Undo not due yet</span></button>`;
  const lateButton = mode === "ignored" ? "" : `<button class="outline-btn with-icon mark-btn" id="assign-mark-late" type="button" title="Mark overdue items done locally. This does not submit coursework." ${late.length ? "" : "disabled"}>${actionIcon("submitted")}<span>Mark overdue done locally (${late.length})</span></button>`;
  return `<div class="row" id="assign-toolbar">
    <button class="outline-btn" id="assign-select" type="button">${selectMode ? "Done selecting" : "Select"}</button>
    <button class="text-btn" id="assign-select-all" type="button">Select all</button>
    ${bulk}
    ${lateButton}
    ${undoButton}
    <span class="muted">Mark done changes WhiteBoard only; submit coursework on Blackboard. Select several items for a bulk update.</span>
  </div>`;
}

function refreshAssignToolbar() {
  const box = document.getElementById("assign-toolbar");
  if (!box) return;
  box.outerHTML = assignToolbar(assignmentMode());
}

let assignmentWrite = 0;
let assignmentQueue = Promise.resolve();

function lateAssignments() {
  reapplyManualMarks();
  const now = Date.now() / 1000;
  return (state.assignments || []).filter((item) =>
    !item.ignored
    && item.status !== "submitted"
    && item.ts
    && item.ts < now
    && keptByHistory(item)
    && inActiveFilter(item.course_id)
  );
}

function notDueMarked() {
  const now = Date.now() / 1000;
  return (state.assignments || []).filter((item) => item.manual && (!item.ts || item.ts > now));
}

function previewUpdates(action, ids) {
  const now = Date.now() / 1000;
  const wanted = new Set(ids || []);
  const updates = [];
  (state.assignments || []).forEach((item) => {
    const hit = action === "undo_not_due"
      ? item.manual && (!item.ts || item.ts > now)
      : wanted.has(item.id);
    if (!hit) return;
    let manual = !!item.manual;
    let ignored = !!item.ignored;
    if (action === "submitted") manual = true;
    else if (action === "unsubmit" || action === "undo_not_due") manual = false;
    else if (action === "ignore") ignored = true;
    else if (action === "restore") ignored = false;
    const base = item.base_status || (item.manual ? "todo" : (item.status || "todo"));
    updates.push({
      id: item.id,
      status: base === "submitted" || manual ? "submitted" : base,
      manual,
      ignored,
    });
  });
  return updates;
}

function applyAssignmentUpdates(updates) {
  const byId = new Map((updates || []).map((row) => [row.id, row]));
  if (!byId.size) return;
  (state.assignments || []).forEach((item) => {
    const next = byId.get(item.id);
    if (!next) return;
    item.status = next.status;
    item.manual = !!next.manual;
    item.ignored = !!next.ignored;
    if ("submitted_ts" in next) item.submitted_ts = next.submitted_ts;
    if (item.manual) manualMarks.add(item.id);
    else manualMarks.delete(item.id);
  });
  const touch = (item) => {
    const next = byId.get(item.assignment_id) || byId.get(item.id);
    if (!next) return;
    Object.assign(item, next);
    item.finished = next.status === "submitted";
  };
  (state.calendar || []).forEach(touch);
  (state.home_due || []).forEach(touch);
  Object.values(state.course_pages || {}).forEach((page) => {
    (page.upcoming || []).forEach(touch);
  });

}

function paintAssignmentSurface() {
  const undo = document.getElementById("cal-undo-open");
  if (undo) undo.disabled = notDueMarked().length === 0;
  updateTodoBadge();
  if (route === "/assignments" || route === "/ignored") {
    refreshAssignToolbar();
    paintListRoot();
    return;
  }
  if (topOf(route) === "/calendar") {
    paintCalendarRoot();
    return;
  }
  paintPage();
}

function changeAssignments(action, ids) {
  if (action !== "undo_not_due" && !(ids && ids.length)) return;
  const token = ++assignmentWrite;
  const before = (state.assignments || []).filter((item) =>
    action === "undo_not_due" || (ids || []).includes(item.id)
  ).map((item) => ({
    id: item.id,
    status: item.status,
    manual: !!item.manual,
    ignored: !!item.ignored,
  }));
  applyAssignmentUpdates(previewUpdates(action, ids));
  if (action !== "undo_not_due") {
    selectedAssignments.clear();
    selectMode = false;
  }
  paintAssignmentSurface();
  assignmentQueue = assignmentQueue.catch(() => {}).then(() => api("/api/assignments", { action, ids: ids || [] })).then(async (result) => {
    if (token !== assignmentWrite) return;
    applyAssignmentUpdates((result && result.updates) || []);
    await loadState();
    paintAssignmentSurface();
  }).catch(async (error) => {
    if (token !== assignmentWrite) return;
    await loadState().catch(() => {});
    jobError = error.message;
    applyAssignmentUpdates(before);
    paintAssignmentSurface();
  });
}

function assignmentFolders(mode) {
  const items = assignmentItems(mode);
  const card = (item) => assignCard(item, true);
  if (mode === "submitted") return paged("assignments-submitted", items, card);
  if (mode === "ignored") {
    return items.length ? paged("assignments-ignored", items, card) : `<p class="empty">No ignored assignments.</p>`;
  }
  const now=Date.now()/1000, archiveBefore=now-180*86400;
  const todo = items.filter(item=>item.status !== "submitted");
  const current=todo.filter(item=>!item.ts || item.ts>=archiveBefore);
  const dueNow=current.filter(item=>item.ts>=now && item.ts<now+86400);
  const upcoming=current.filter(item=>!item.ts || item.ts>=now+86400);
  const overdue=current.filter(item=>item.ts && item.ts<now).sort((a,b)=>b.ts-a.ts);
  const archived=todo.filter(item=>item.ts && item.ts<archiveBefore).sort((a,b)=>b.ts-a.ts);
  const done=items.filter(item=>item.status === "submitted");
  return `<p class="muted">${items.length} results · Older work stays available in Archived (over 6 months old).</p>${folder("now","Due in 24 hours",dueNow,card)}${folder("upcoming","Upcoming and undated",upcoming,card)}${folder("overdue","Overdue",overdue,card)}${folder("archived","Archived",archived,card)}${folder("submitted","Completed",done,card)}`;
}

function assignmentView(id) {
  const item = state.assignments.find((row) => row.id === id);
  if (!item) return `<h2>Assignment</h2><p class="muted">Not in the saved dashboard.</p>`;
  const back = detailReturn || "/assignments";
  const backLabel = back === "/calendar" ? "Back to calendar" : "Back";
  return `<button class="text-btn" data-go="${back}">${backLabel}</button>
    <h2>${escapeHtml(item.title)}</h2>
    ${assignCard(item, true)}
    ${item.description ? `<div class="card"><p class="muted">Description</p><p>${escapeHtml(item.description)}</p></div>` : ""}`;
}

function gradesView() {
  const allowed = new Set(shownCourses().map((course) => course.id));
  const lines = (state.score_lines || []).filter((line) => allowed.has(line.id)).map((line) => `<div style="margin:12px 0">
      <div class="row"><span class="swatch" style="border-color:${line.ink};background:${line.fill}"></span><strong>${escapeHtml(line.name)}</strong><span class="spacer"></span><span>${line.percent}%</span></div>
      <div class="bar"><span data-bar="${line.percent}" style="background:${line.ink}"></span></div>
    </div>`).join("");
  return `<h2>Grades</h2><p class="muted">Posted scores and submitted work waiting for a grade.</p>
    ${searchBox("grades", "Search grades")}
    ${lines}
    <div id="list-root">${gradesLists()}</div>
    ${feedback ? feedbackModal() : ""}`;
}

function gradesLists() {
  const needle = query.grades.toLowerCase();
  const match = (grade) => inActiveFilter(grade.course_id) && `${grade.title} ${grade.course} ${grade.label} ${grade.note}`.toLowerCase().includes(needle);
  return `${folder("graded", "Graded", state.graded.filter(match), gradeCard)}
    ${folder("pending", "Submitted, not graded", state.pending.filter(match), gradeCard)}`;
}

function courseView(id) {
  ensureLazyCourse(id);
  const course = state.courses.find((item) => item.id === id);
  const page = (state.course_pages || {})[id];
  if (!course || !page) return `<h2>Course</h2><p class="muted">No course data.</p>`;
  const ring = page.percent == null ? "" : `<div>${ringSvg(page.percent)}<div class="muted" style="text-align:center">${escapeHtml(page.fraction)}</div></div>`;
  const upcoming = (page.upcoming || []).filter(keptByHistory).map((item) => assignCard(item, true)).join("") || `<p class="empty">No upcoming work for this course.</p>`;
  const grades = page.grades.map((row) => `<div class="card row"><div><strong>${escapeHtml(row.title)}</strong><div class="muted">${escapeHtml(row.due)}</div></div><span class="spacer"></span><strong>${escapeHtml(row.label)}</strong></div>`).join("") || `<p class="empty">No grades for this course yet.</p>`;
  return `<div class="score-row"><h2>${escapeHtml(course.name)}</h2>${ring}</div>
    <h3>Upcoming work</h3>${upcoming}<h3>Grades</h3>${grades}`;
}

function calendarView() {
  return `<h2>Calendar</h2>
    <p class="muted">Assignments, tests, and other Blackboard calendar events.</p>
    ${legend()}
    ${calendarToolbar()}
    <div id="calendar-root">${calendarBody()}</div>`;
}

function calendarToolbar() {
  const modes = [["list", "List"], ["week", "Week"], ["month", "Month"]]
    .map(([key, label]) => `<button class="chip-btn ${calendarMode === key ? "active" : ""}" data-cal-mode="${key}">${label}</button>`)
    .join("");
  const days = calendarMode === "list"
    ? `<div class="row">${[7, 14, 30].map((n) => `<button class="chip-btn ${calendarDays === n ? "active" : ""}" data-cal-days="${n}">${n} days</button>`).join("")}</div>`
    : "";
  return `<div class="cal-toolbar">
    <div class="row">
      <button class="outline-btn" id="cal-today">Today</button>
      <button class="outline-btn" id="cal-prev" aria-label="Previous">‹</button>
      <button class="outline-btn" id="cal-next" aria-label="Next">›</button>
      <strong id="cal-period">${escapeHtml(periodTitle())}</strong>
    </div>
    <div class="row">${modes}
      <button class="chip-btn ${hideEvents ? "active" : ""}" id="hide-events" type="button">Hide events</button>
      <button class="outline-btn with-icon" id="cal-undo-open" type="button" title="Clear the submitted mark on every item that is not due yet." ${notDueMarked().length ? "" : "disabled"}>${actionIcon("undo")}<span>Undo not due yet</span></button>
    </div>
    ${days}
  </div>`;
}

function calendarBody() {
  if (calendarDay) {
    const items=visibleEvents(state.calendar.filter(item=>item.day===calendarDay || (item.ts && isoDate(new Date(item.ts*1000))===calendarDay)));
    return `<button id="cal-day-back" class="text-btn">Back to calendar</button><h3>${escapeHtml(calendarDay)}</h3>${items.map(item=>assignCard(item, false)).join("")}`;
  }
  if (calendarMode === "month") return monthGrid();
  if (calendarMode === "week") return weekGrid();
  return calendarList();
}

function visibleEvents(items) {
  return items.filter((item) => {
    if (!keptByHistory(item)) return false;
    if (hideEvents && item.kind === "other") return false;
    if (!item.course_id) return true;
    return inActiveFilter(item.course_id);
  });
}

function calendarList() {
  const origin = calendarAnchor.getTime() === startOfDay(new Date()).getTime()
    ? Date.now()
    : calendarAnchor.getTime();
  const limit = origin + calendarDays * 86400000;
  const items = visibleEvents(state.calendar.filter((item) => {
    const ts = (item.ts || 0) * 1000;
    return ts >= origin - 12 * 3600000 && ts <= limit;
  })).sort((a, b) => (a.ts || 0) - (b.ts || 0));
  if (!items.length) return `<p class="empty">No upcoming events in this range.</p>`;
  const size = pageSize;
  const key = "calendar-list";
  const page = Math.min(pages[key] || 0, Math.max(0, Math.ceil(items.length / size) - 1));
  pages[key] = page;
  const slice = items.slice(page * size, page * size + size);
  let last = "";
  const blocks = slice.map((item) => {
    const head = item.day_label !== last ? `<h3>${escapeHtml(item.day_label)}</h3>` : "";
    last = item.day_label;
    return head + assignCard(item);
  }).join("");
  return blocks + pager(key, items.length, page, size);
}

function monthGrid() {
  const monthStart = new Date(calendarAnchor.getFullYear(), calendarAnchor.getMonth(), 1);
  const gridStart = weekStart(monthStart);
  const monthEnd = addMonths(monthStart, 1);
  const rangeEnd = addDays(gridStart, 42);
  const byDay = eventsByDay(gridStart, rangeEnd);
  const today = startOfDay(new Date()).getTime();
  const header = WEEKDAYS.map((name) => `<span>${name}</span>`).join("");
  let rows = "";
  for (let week = 0; week < 6; week += 1) {
    let cells = "";
    for (let offset = 0; offset < 7; offset += 1) {
      const day = addDays(gridStart, week * 7 + offset);
      const inMonth = day >= monthStart && day < monthEnd;
      const isToday = day.getTime() === today;
      const events = (byDay.get(isoDate(day)) || []).slice(0, 3);
      const extra = (byDay.get(isoDate(day)) || []).length - events.length;
      cells += `<div class="cal-cell ${inMonth ? "" : "out"} ${isToday ? "today" : ""}">
        <div class="day-num">${day.getDate()}</div>
        ${events.map((item) => eventChip(item)).join("")}
        ${extra > 0 ? `<button class="text-btn" data-cal-day="${isoDate(day)}" aria-label="Show all events on ${isoDate(day)}">+${extra} more</button>` : ""}
      </div>`;
    }
    rows += `<div class="cal-row">${cells}</div>`;
  }
  return `<div class="cal-grid"><div class="cal-weekdays">${header}</div>${rows}</div>`;
}

function weekGrid() {
  const start = weekStart(calendarAnchor);
  const today = startOfDay(new Date()).getTime();
  const byDay = eventsByDay(start, addDays(start, 7));
  const heads = Array.from({ length: 7 }, (_, i) => {
    const day = addDays(start, i);
    const isToday = day.getTime() === today;
    return `<div class="week-head"><div class="muted">${WEEKDAYS[i]}</div><div class="week-num ${isToday ? "today" : ""}">${day.getDate()}</div></div>`;
  }).join("");
  const allDay = Array.from({ length: 7 }, (_, i) => {
    const items = (byDay.get(isoDate(addDays(start, i))) || []).filter((item) => item.all_day);
    return `<div class="week-stack">${items.map((item) => eventChip(item)).join("") || '<span class="muted">All day</span>'}</div>`;
  }).join("");
  const timed = Array.from({ length: 7 }, (_, i) => {
    const items = (byDay.get(isoDate(addDays(start, i))) || []).filter((item) => !item.all_day);
    return `<div class="week-stack timed">${items.map((item) => eventChip(item, true)).join("")}</div>`;
  }).join("");
  return `<div class="week-grid">
    <div class="week-row">${heads}</div>
    <div class="week-label muted">All-day</div>
    <div class="week-row">${allDay}</div>
    <div class="week-row">${timed}</div>
  </div>`;
}

function eventsByDay(start, end) {
  const map = new Map();
  visibleEvents(state.calendar).forEach((item) => {
    if (!item.day) return;
    const ts = (item.ts || 0) * 1000;
    if (ts < start.getTime() || ts >= end.getTime()) return;
    if (!map.has(item.day)) map.set(item.day, []);
    map.get(item.day).push(item);
  });
  return map;
}

function eventChip(item, showTime) {
  const dest = calendarDest(item);
  const fill = item.kind === "other" ? "var(--event-bg)" : (item.finished ? "#e2e8f0" : item.fill);
  const ink = item.kind === "other" ? "var(--event)" : (item.finished ? "var(--muted)" : item.ink || "var(--text)");
  const label = showTime && item.time ? `${item.time} ${item.title}` : item.title;
  return `<button class="event-chip" style="background:${fill};color:${ink}" data-go="${dest}">${escapeHtml(label)}</button>`;
}

function calendarDest(item) {
  const aid = item.assignment_id || item.id;
  if (aid && state.assignments.some((row) => row.id === aid)) return `/assignments/${encodeURIComponent(aid)}`;
  if (item.course_id) return `/courses/${encodeURIComponent(item.course_id)}`;
  return "/calendar";
}

function periodTitle() {
  if (calendarMode === "month") {
    return calendarAnchor.toLocaleString("en-GB", { month: "long", year: "numeric" });
  }
  if (calendarMode === "week") {
    const start = weekStart(calendarAnchor);
    const end = addDays(start, 6);
    if (start.getMonth() === end.getMonth()) {
      return `${start.toLocaleString("en-GB", { month: "short" })} ${start.getDate()} – ${end.getDate()}, ${end.getFullYear()}`;
    }
    return `${start.toLocaleString("en-GB", { month: "short" })} ${start.getDate()} – ${end.toLocaleString("en-GB", { month: "short" })} ${end.getDate()}, ${end.getFullYear()}`;
  }
  if (calendarAnchor.getTime() === startOfDay(new Date()).getTime()) return `Next ${calendarDays} days`;
  return `From ${calendarAnchor.toLocaleString("en-GB", { month: "short" })} ${calendarAnchor.getDate()}`;
}

function shiftCalendar(delta) {
  if (calendarMode === "month") calendarAnchor = addMonths(calendarAnchor, delta);
  else if (calendarMode === "week") calendarAnchor = addDays(calendarAnchor, delta * 7);
  else calendarAnchor = addDays(calendarAnchor, delta * calendarDays);
}

function contentsView() {
  return `<h2>Contents</h2>
    <p class="muted">Course files. Metadata loads with Refresh; files download only when you choose Download.</p>
    <div class="row">
      ${["tree", "folder", "columns"].map((mode) => {
        const label = mode[0].toUpperCase() + mode.slice(1);
        return `<button class="${contentsMode === mode ? "fill-btn" : "outline-btn"}" data-contents-mode="${mode}">${label}</button>`;
      }).join("")}
    </div>
    <div class="row" style="margin-top:8px">
      <button class="fill-btn" id="contents-download" type="button" ${contentsSelected.size || contentsFolders.size ? "" : "disabled"}>Download</button>
      <button class="outline-btn" id="contents-open-selected" type="button" ${contentsSelected.size ? "" : "disabled"}>Open</button>
      <button class="outline-btn ${contentsOnlySelected ? "fill-btn" : ""}" id="contents-view-selected" type="button">View currently selected</button>
      <span class="muted" id="contents-note">${escapeHtml(contentsNote || (contentsSelected.size ? `${contentsSelected.size} selected` : "Select files to download or open. Shift-click or drag to select a section."))}</span>
    </div>
    <div class="row">
      <input class="search" id="contents-search" placeholder="Search folder, file name, or extension" value="${escapeAttr(query.contents || "")}" />
      <button class="outline-btn ${contentsSearchHere ? "fill-btn" : ""}" id="contents-search-here" type="button">Only this folder</button>
    </div>
    <div id="contents-root">${contentsBody()}</div>`;
}

function ensureContentIndex() {
  const nodes = (state && state.content_nodes) || [];
  if (contentIndex && contentIndex.source === nodes) return contentIndex;
  const byParent = new Map();
  const byCourse = new Map();
  const byId = new Map();
  nodes.forEach((node) => {
    byId.set(node.id, node);
    const courseList = byCourse.get(node.course_id);
    if (courseList) courseList.push(node);
    else byCourse.set(node.course_id, [node]);
    const key = `${node.course_id}\n${node.parent_id || ""}`;
    const siblings = byParent.get(key);
    if (siblings) siblings.push(node);
    else byParent.set(key, [node]);
  });
  byParent.forEach((list) => {
    list.sort((a, b) => (a.kind === "folder" ? 0 : 1) - (b.kind === "folder" ? 0 : 1) || a.name.localeCompare(b.name));
  });
  contentIndex = { source: nodes, byParent, byCourse, byId };
  return contentIndex;
}

function nodesForCourses(courses) {
  const index = ensureContentIndex();
  const out = [];
  courses.forEach((course) => {
    const list = index.byCourse.get(course.id);
    if (list) out.push(...list);
  });
  return out;
}

function contentsBody() {
  const courses = shownCourses();
  const nodes = nodesForCourses(courses);
  if (contentsOnlySelected) return selectedContentsView(courses, nodes);
  const needle = (query.contents || "").trim();
  if (needle) return contentsSearchView(courses, nodes, needle);
  if (!courses.length) return `<p class="empty">No courses in this filter.</p>`;
  const hint = !nodes.length
    ? `<p class="empty">${state.files_indexed
      ? "No course files indexed yet. Use Refresh after signing in."
      : "Course files load when you open this page. Sign in, or use Refresh to index everything."}</p>`
    : "";
  if (contentsMode === "folder") return hint + folderView(courses, nodes);
  if (contentsMode === "columns") return hint + columnsView(courses, nodes);
  return hint + treeView(courses, nodes);
}

function nodeMatches(node, needle) {
  const raw = needle.trim().toLowerCase();
  if (!raw) return true;
  const name = (node.name || "").toLowerCase();
  if (name.includes(raw)) return true;
  if (node.kind === "folder") return false;
  const ext = String(node.extension || "").replace(/^\./, "").toLowerCase();
  const bare = raw.replace(/^\./, "");
  return !!ext && ext === bare;
}

function currentFolderNodes(nodes) {
  if (!contentsSearchHere) return nodes;
  const key = contentsPath[contentsPath.length - 1];
  if (!key) return nodes;
  if (key.startsWith("course:")) {
    const courseId = key.slice(7);
    return nodes.filter((node) => node.course_id === courseId);
  }
  const folder = nodes.find((node) => node.id === key);
  if (!folder) return nodes;
  const allowed = new Set([folder.id]);
  const walk = (parentId) => {
    contentChildren(nodes, folder.course_id, parentId).forEach((node) => {
      allowed.add(node.id);
      if (node.kind === "folder") walk(node.id);
    });
  };
  walk(folder.id);
  return nodes.filter((node) => allowed.has(node.id));
}

function folderTrail(nodes, node) {
  const names = [];
  let parent = node.parent_id || "";
  const seen = new Set();
  while (parent && !seen.has(parent)) {
    seen.add(parent);
    const folder = ensureContentIndex().byId.get(parent);
    if (!folder) break;
    names.unshift(folder.name);
    parent = folder.parent_id || "";
  }
  return names.join(" / ");
}

function contentsSearchView(courses, nodes, needle) {
  const scoped = currentFolderNodes(nodes);
  const courseHits = contentsSearchHere ? [] : courses
    .filter((course) => course.name.toLowerCase().includes(needle.toLowerCase()))
    .map((course) => ({
      key: `course:${course.id}`,
      name: course.name,
      kind: "folder",
      path: "Courses",
      node: null,
    }));
  const fileHits = scoped.filter((node) => nodeMatches(node, needle)).map((node) => {
    const course = courses.find((item) => item.id === node.course_id);
    const trail = folderTrail(nodes, node);
    const where = [course ? course.name : "", trail].filter(Boolean).join(" / ");
    return {
      key: node.id,
      name: node.name,
      kind: node.kind === "folder" ? "folder" : (node.extension || "file"),
      path: where || "Courses",
      node,
    };
  });
  const items = sortSearchHits(courseHits.concat(fileHits));
  if (!items.length) return `<p class="empty">No folders or files match that search.</p>`;
  const key = "contents-search";
  const size = pageSize;
  const page = Math.min(pages[key] || 0, Math.max(0, Math.ceil(items.length / size) - 1));
  pages[key] = page;
  const shown = items.slice(page * size, page * size + size);
  const rows = shown.map((item) => {
    const reveal = item.kind === "folder" ? `data-reveal="${escapeAttr(item.key)}"` : "";
    const selected = item.node && (item.node.kind === "folder" ? folderSelected(item.node) : contentsSelected.has(item.node.id));
    const check = item.node
      ? `<label data-select="${escapeAttr(item.node.id)}"><input type="checkbox" ${selected ? "checked" : ""} /></label>`
      : `<span></span>`;
    const icon = item.kind === "folder" ? folderSvg(false) : fileSvg(item.node);
    const openBtn = item.node && item.node.kind !== "folder"
      ? `<button class="text-btn" data-open="${escapeAttr(item.node.url)}" data-title="${escapeAttr(item.node.name)}">${openSvg()}</button>`
      : `<span></span>`;
    const extRaw = item.node && item.node.kind !== "folder"
      ? String(item.node.extension || "").replace(/^\./, "")
      : "";
    const showExt = extRaw && !item.name.toLowerCase().endsWith(`.${extRaw.toLowerCase()}`);
    const ext = showExt ? `<span class="muted">.${escapeHtml(extRaw)}</span>` : "";
    return `<div class="file-row ${selected ? "selected" : ""}" ${item.node ? `data-row-id="${escapeAttr(item.node.id)}"` : ""}>
      <span></span>${check}<span ${reveal}>${icon}</span>
      <span class="name stack ${item.kind === "folder" ? "folder" : ""}" ${reveal}>
        ${escapeHtml(item.name)} ${ext}
        <span class="path">${escapeHtml(item.path)}</span>
      </span>
      <span class="muted">${item.node && item.node.kind !== "folder" ? escapeHtml(item.node.size_label) : "—"}</span>
      <span class="muted">${item.node ? escapeHtml(item.node.date) : "—"}</span>
      ${openBtn}
    </div>`;
  }).join("");
  return `${fileHeader()}${rows}${pager(key, items.length, page, size)}`;
}

function revealContent(key) {
  query.contents = "";
  const nodes = state.content_nodes || [];
  if (key.startsWith("course:")) {
    contentsPath = [key];
    contentsExpanded.add(key);
  } else {
    const node = nodes.find((item) => item.id === key);
    if (!node) return;
    const chain = [];
    let cursor = node.kind === "folder" ? node.id : (node.parent_id || "");
    const seen = new Set();
    while (cursor && !seen.has(cursor)) {
      seen.add(cursor);
      chain.unshift(cursor);
      const folder = nodes.find((item) => item.id === cursor);
      cursor = folder ? (folder.parent_id || "") : "";
    }
    contentsPath = [`course:${node.course_id}`, ...chain];
    contentsExpanded.add(`course:${node.course_id}`);
    chain.forEach((id) => contentsExpanded.add(id));
  }
  paintPage();
}

function treeView(courses, nodes) {
  const size = pageSize;
  const key = "contents-tree";
  const page = Math.min(pages[key] || 0, Math.max(0, Math.ceil(courses.length / size) - 1));
  pages[key] = page;
  const shown = courses.slice(page * size, page * size + size);
  const header = fileHeader();
  const rows = shown.flatMap((course) => {
    const courseKey = `course:${course.id}`;
    const expanded = contentsExpanded.has(courseKey);
    const bits = [folderRow(courseKey, course.name, 0, expanded, "—", "", true)];
    if (expanded) bits.push(treeRows(nodes, course.id, "", 1));
    return bits;
  });
  return header + rows.join("") + pager(key, courses.length, page, size);
}

function treeRows(nodes, courseId, parentId, depth) {
  return contentChildren(nodes, courseId, parentId).map((node) => {
    if (node.kind === "folder") {
      const expanded = contentsExpanded.has(node.id);
      const row = folderRow(node.id, node.name, depth, expanded, "—", node.date, false, node);
      return row + (expanded ? treeRows(nodes, courseId, node.id, depth + 1) : "");
    }
    return fileRow(node, depth);
  }).join("");
}

function folderView(courses, nodes) {
  const parentKey = contentsPath[contentsPath.length - 1] || null;
  const items = explorerItems(courses, nodes, parentKey);
  if (!items.length) {
    const empty = parentKey == null && !nodes.length
      ? "No course files indexed yet. Use Refresh after signing in."
      : "This folder is empty.";
    return `${breadcrumb(courses, nodes)}${fileHeader()}<p class="empty">${empty}</p>`;
  }
  const key = `contents-folder:${parentKey || "root"}`;
  const size = pageSize;
  const page = Math.min(pages[key] || 0, Math.max(0, Math.ceil(items.length / size) - 1));
  pages[key] = page;
  const shown = items.slice(page * size, page * size + size);
  return `${breadcrumb(courses, nodes)}${fileHeader()}${shown.map((item) => explorerRow(item, parentKey, true)).join("")}${pager(key, items.length, page, size)}`;
}

function columnsView(courses, nodes) {
  const specs = millerColumns(contentsPath);
  const cols = specs.map(([parentKey, selectedKey]) => {
    const items = explorerItems(courses, nodes, parentKey);
    const title = parentKey == null ? "Courses" : pathLabel(courses, nodes, parentKey);
    const key = `contents-col:${parentKey || "root"}`;
    const size = pageSize;
    const selectedIndex = items.findIndex((item) => item.key === selectedKey);
    let page = pages[key] || 0;
    if (selectedIndex >= 0) page = Math.floor(selectedIndex / size);
    const pageCount = Math.max(1, Math.ceil(items.length / size));
    page = Math.min(page, pageCount - 1);
    pages[key] = page;
    const shown = items.slice(page * size, page * size + size);
    const body = shown.map((item) => explorerRow(item, parentKey, false, item.key === selectedKey)).join("")
      || `<div class="muted" style="padding:12px">Empty</div>`;
    return `<div class="column"><h4>${escapeHtml(title)}</h4><div class="body">${body}${pager(key, items.length, page, size)}</div></div>`;
  });
  while (cols.length < 3) cols.push(`<div class="column"></div>`);
  return `${breadcrumb(courses, nodes)}<div class="columns">${cols.join("")}</div>`;
}

function explorerItems(courses, nodes, parentKey) {
  if (parentKey == null) {
    return courses.map((course) => ({
      key: `course:${course.id}`,
      name: course.name,
      isFolder: true,
      isCourse: true,
      node: null,
    }));
  }
  if (parentKey.startsWith("course:")) {
    return contentChildren(nodes, parentKey.slice(7), "").map(nodeToItem);
  }
  const folder = nodes.find((node) => node.id === parentKey);
  if (!folder) return [];
  return contentChildren(nodes, folder.course_id, folder.id).map(nodeToItem);
}

function nodeToItem(node) {
  return {
    key: node.id,
    name: node.name,
    isFolder: node.kind === "folder",
    isCourse: false,
    node,
  };
}

function explorerRow(item, parentKey, showMeta, highlighted) {
  const selected = item.node && !item.isFolder && contentsSelected.has(item.node.id);
  const cls = [highlighted ? "hi" : "", selected ? "selected" : ""].filter(Boolean).join(" ");
  const open = item.isFolder ? `data-contents-open="${escapeAttr(item.key)}" data-contents-parent="${escapeAttr(parentKey || "")}"` : "";
  const check = item.isCourse
    ? `<span></span>`
    : `<label data-select="${escapeAttr(item.node ? item.node.id : "")}"><input type="checkbox" ${selected ? "checked" : ""} ${item.node ? "" : "disabled"} /></label>`;
  const icon = item.isFolder ? folderSvg(false) : fileSvg(item.node);
  const meta = showMeta
    ? `<span class="muted">${item.isFolder ? "—" : escapeHtml(item.node ? item.node.size_label : "—")}</span>
       <span class="muted">${item.node ? escapeHtml(item.node.date) : "—"}</span>`
    : "";
  const openBtn = item.node && !item.isFolder
    ? `<button class="text-btn" data-open="${escapeAttr(item.node.url)}">${openSvg()}</button>`
    : `<span></span>`;
  return `<div class="file-row ${cls}" ${item.node ? `data-row-id="${escapeAttr(item.node.id)}"` : ""}>
    <span></span>${check}<span ${open}>${icon}</span>
    <span class="name ${item.isFolder ? "folder" : ""}" ${open}>${escapeHtml(item.name)}</span>
    ${meta}${openBtn}
  </div>`;
}

function folderRow(key, name, depth, expanded, sizeLabel, dateLabel, isCourse, node) {
  const pad = 8 + depth * 16;
  const selected = node && folderSelected(node);
  const check = isCourse
    ? `<span></span>`
    : `<label data-select="${escapeAttr(node.id)}"><input type="checkbox" ${selected ? "checked" : ""} /></label>`;
  return `<div class="file-row ${selected ? "selected" : depth % 2 ? "alt" : ""}" style="padding-left:${pad}px" ${node ? `data-row-id="${escapeAttr(node.id)}"` : ""}>
    <button class="chevron" data-expand="${escapeAttr(key)}">${expanded ? "▾" : "▸"}</button>
    ${check}
    ${folderSvg(expanded)}
    <span class="name folder">${escapeHtml(name)}</span>
    <span class="muted">${escapeHtml(sizeLabel)}</span>
    <span class="muted">${escapeHtml(dateLabel || "—")}</span>
    <span></span>
  </div>`;
}

function fileRow(node, depth) {
  const selected = contentsSelected.has(node.id);
  const pad = 8 + depth * 16;
  return `<div class="file-row ${selected ? "selected" : depth % 2 ? "alt" : ""}" style="padding-left:${pad}px" data-row-id="${escapeAttr(node.id)}">
    <span></span>
    <label data-select="${escapeAttr(node.id)}"><input type="checkbox" ${selected ? "checked" : ""} /></label>
    ${fileSvg(node)}
    <span class="name">${escapeHtml(node.name)}</span>
    <span class="muted">${escapeHtml(node.size_label)}</span>
    <span class="muted">${escapeHtml(node.date)}</span>
    <button class="text-btn" data-open="${escapeAttr(node.url)}">${openSvg()}</button>
  </div>`;
}

function fileHeader() {
  const mark = (key, label) => {
    const active = contentsSort.key === key;
    const arrow = active ? (contentsSort.dir > 0 ? " ↑" : " ↓") : "";
    return `<button type="button" data-sort="${key}">${label}${arrow}</button>`;
  };
  return `<div class="file-header"><span></span><span></span>${mark("type", "Type")}${mark("name", "Name")}<span>Size</span>${mark("date", "Date uploaded")}<span></span></div>`;
}

function breadcrumb(courses, nodes) {
  const crumbs = [`<button data-crumb="-1">Courses</button>`];
  contentsPath.forEach((key, index) => {
    crumbs.push(`<span class="muted">/</span><button data-crumb="${index}">${escapeHtml(pathLabel(courses, nodes, key))}</button>`);
  });
  return `<div class="crumb">
    <button class="outline-btn" id="contents-up" ${contentsPath.length ? "" : "disabled"}>Up</button>
    ${crumbs.join("")}
  </div>`;
}

function pathLabel(courses, nodes, key) {
  if (key.startsWith("course:")) {
    const course = courses.find((item) => item.id === key.slice(7));
    return course ? course.name : key;
  }
  const node = nodes.find((item) => item.id === key);
  return node ? node.name : key;
}

function contentsOpenFolder(parentKey, childKey) {
  if (!parentKey) {
    contentsPath = [childKey];
    return;
  }
  const index = contentsPath.indexOf(parentKey);
  contentsPath = index >= 0 ? contentsPath.slice(0, index + 1).concat(childKey) : [parentKey, childKey];
}

function millerColumns(path) {
  const n = Math.min(3, path.length + 1);
  const start = path.length + 1 - n;
  const columns = [];
  for (let offset = 0; offset < n; offset += 1) {
    const parentIndex = start + offset - 1;
    const parentKey = parentIndex < 0 ? null : path[parentIndex];
    const selected = start + offset < path.length ? path[start + offset] : null;
    columns.push([parentKey, selected]);
  }
  return columns;
}

function contentChildren(_nodes, courseId, parentId) {
  const index = ensureContentIndex();
  return sortContentList(index.byParent.get(`${courseId}\n${parentId || ""}`) || []);
}

function fileTypeKey(node) {
  if (!node || node.kind === "folder") return "folder";
  return String(node.extension || node.kind || "file").replace(/^\./, "").toLowerCase();
}

function sortContentList(list) {
  const dir = contentsSort.dir || 1;
  return list.slice().sort((a, b) => {
    const folder = (a.kind === "folder" ? 0 : 1) - (b.kind === "folder" ? 0 : 1);
    if (folder) return folder;
    let cmp = 0;
    if (contentsSort.key === "type") cmp = fileTypeKey(a).localeCompare(fileTypeKey(b));
    else if (contentsSort.key === "date") cmp = (a.date_ts || 0) - (b.date_ts || 0);
    else cmp = (a.name || "").localeCompare(b.name || "");
    if (!cmp) cmp = (a.name || "").localeCompare(b.name || "");
    return cmp * dir;
  });
}

function sortSearchHits(list) {
  const dir = contentsSort.dir || 1;
  return list.slice().sort((a, b) => {
    const folder = (a.kind === "folder" ? 0 : 1) - (b.kind === "folder" ? 0 : 1);
    if (folder) return folder;
    let cmp = 0;
    if (contentsSort.key === "type") {
      cmp = String(a.kind || "").localeCompare(String(b.kind || ""));
    } else if (contentsSort.key === "date") {
      cmp = ((a.node && a.node.date_ts) || 0) - ((b.node && b.node.date_ts) || 0);
    } else cmp = (a.name || "").localeCompare(b.name || "");
    if (!cmp) cmp = (a.name || "").localeCompare(b.name || "");
    return cmp * dir;
  });
}

function selectedContentsView(courses, nodes) {
  const picked = nodes.filter((node) => contentsSelected.has(node.id) || contentsFolders.has(node.id) || (node.kind === "folder" && folderSelected(node)));
  if (!picked.length) return `<p class="empty">Nothing is selected.</p>`;
  const rows = sortContentList(picked).map((node) => (
    node.kind === "folder"
      ? folderRow(node.id, node.name, 0, false, "—", node.date, false, node)
      : fileRow(node, 0)
  )).join("");
  return `${fileHeader()}${rows}`;
}

function descendantFiles(folder) {
  const nodes = state.content_nodes || [];
  const found = [];
  const walk = (parentId) => {
    contentChildren(nodes, folder.course_id, parentId).forEach((node) => {
      if (node.kind === "folder") walk(node.id);
      else found.push(node);
    });
  };
  walk(folder.id);
  return found;
}

function folderSelected(folder) {
  const files = descendantFiles(folder);
  return files.length > 0 && files.every((node) => contentsSelected.has(node.id));
}

function toggleContentSelected(id, checked) {
  const node = ensureContentIndex().byId.get(id);
  if (!node) return;
  if (node.kind === "folder") {
    if (checked) contentsFolders.add(node.id);
    else contentsFolders.delete(node.id);
  }
  const targets = node.kind === "folder" ? descendantFiles(node) : [node];
  targets.forEach((item) => {
    if (checked) contentsSelected.add(item.id);
    else contentsSelected.delete(item.id);
  });
  if (!checked && node.kind !== "folder") {
    contentsFolders.forEach((folderId) => {
      const folder = ensureContentIndex().byId.get(folderId);
      if (folder && !folderSelected(folder)) contentsFolders.delete(folderId);
    });
  }
}

function selectContentsRange(fromId, toId) {
  const rows = [...document.querySelectorAll("#contents-root .file-row[data-row-id]")];
  const ids = rows.map((row) => row.dataset.rowId);
  let start = ids.indexOf(fromId);
  let end = ids.indexOf(toId);
  if (end < 0) return;
  if (start < 0) start = end;
  const [left, right] = start < end ? [start, end] : [end, start];
  contentsSelected.clear();
  contentsFolders.clear();
  for (let index = left; index <= right; index += 1) toggleContentSelected(ids[index], true);
  contentsAnchor = toId;
  refreshContentsSelection();
}

function refreshContentsSelection() {
  paintContentsRoot();
  const note = document.getElementById("contents-note");
  if (note) {
    note.textContent = contentsNote || (contentsSelected.size
      ? `${contentsSelected.size} selected`
      : "Select files to download or open. Shift-click or drag to select a section.");
  }
  ["contents-download", "contents-open-selected"].forEach((id) => {
    const button = document.getElementById(id);
    if (button) button.disabled = id === "contents-download"
      ? contentsSelected.size === 0 && contentsFolders.size === 0
      : contentsSelected.size === 0;
  });
}

function onContentsPointerDown(event) {
  if (route !== "/contents" || event.button !== 0) return;
  const row = event.target.closest && event.target.closest("#contents-root .file-row[data-row-id]");
  if (!row) return;
  if (event.shiftKey) {
    event.preventDefault();
    selectContentsRange(contentsAnchor || row.dataset.rowId, row.dataset.rowId);
    contentsDrag = null;
    return;
  }
  if (event.target.closest("button, input, a")) return;
  contentsDrag = {
    x: event.clientX,
    y: event.clientY,
    moved: false,
    additive: false,
  };
}

function onContentsPointerMove(event) {
  if (!contentsDrag) return;
  const dx = event.clientX - contentsDrag.x;
  const dy = event.clientY - contentsDrag.y;
  if (!contentsDrag.moved && dx * dx + dy * dy < 25) return;
  contentsDrag.moved = true;
  paintContentsMarquee(contentsDrag.x, contentsDrag.y, event.clientX, event.clientY);
}

function onContentsPointerUp(event) {
  if (!contentsDrag) return;
  const drag = contentsDrag;
  contentsDrag = null;
  const box = document.getElementById("contents-marquee");
  if (box) box.remove();
  if (!drag.moved) return;
  const left = Math.min(drag.x, event.clientX);
  const right = Math.max(drag.x, event.clientX);
  const top = Math.min(drag.y, event.clientY);
  const bottom = Math.max(drag.y, event.clientY);
  const hits = [...document.querySelectorAll("#contents-root .file-row[data-row-id]")].filter((row) => {
    const rect = row.getBoundingClientRect();
    return rect.right >= left && rect.left <= right && rect.bottom >= top && rect.top <= bottom;
  }).map((row) => row.dataset.rowId);
  if (!drag.additive) {
    contentsSelected.clear();
    contentsFolders.clear();
  }
  hits.forEach((id) => toggleContentSelected(id, true));
  if (hits.length) contentsAnchor = hits[hits.length - 1];
  refreshContentsSelection();
}

function paintContentsMarquee(x1, y1, x2, y2) {
  let box = document.getElementById("contents-marquee");
  if (!box) {
    box = document.createElement("div");
    box.id = "contents-marquee";
    document.body.appendChild(box);
  }
  box.style.left = `${Math.min(x1, x2)}px`;
  box.style.top = `${Math.min(y1, y2)}px`;
  box.style.width = `${Math.abs(x2 - x1)}px`;
  box.style.height = `${Math.abs(y2 - y1)}px`;
}

function settingsView() {
  const colors = state.deadline_colors || {};
  const swatches = Object.entries({ overdue: "Overdue", today: "Due today", soon: "Within 3 days", week: "This week", later: "Later" })
    .map(([key, label]) => `<div class="row">
      <span class="color-dot" style="border:4px solid ${colors[key]}"></span>
      <span style="width:130px">${label}</span>
      <span class="muted">${colors[key] || ""}</span>
      <button class="text-btn" data-deadline-color="${key}" data-deadline-label="${escapeAttr(label)}" data-deadline-current="${escapeAttr(colors[key] || "")}">Change</button>
    </div>`).join("");
  const google = state.google || {};
  const signed = google.signed_in;
  const who = signed && google.email ? `Signed in as ${google.email}` : signed ? "Signed in to Google." : "Not signed in.";
  const courseColors = state.courses.map((course) => `<div class="card">
    <div class="row">
      <span class="color-dot" style="background:${course.fill};border:3px solid ${course.ink}"></span>
      <span style="flex:1">${escapeHtml(course.name)}</span>
      <button class="text-btn" data-course-color="${escapeAttr(course.id)}" data-course-name="${escapeAttr(course.name)}" data-course-current="${escapeAttr(course.ink)}">Change</button>
      ${course.custom ? `<button class="text-btn" data-reset-course="${escapeAttr(course.id)}">Reset</button>` : ""}
    </div>
  </div>`).join("") || `<div class="card"><p class="muted">Sign in and refresh to choose course colors.</p></div>`;
  return `<h2>Settings</h2>
    <div class="card">
      <label>Blackboard base URL</label>
      <input class="settings-input" type="text" value="${escapeAttr(state.base_url || "")}" readonly />
      <p class="muted">${escapeHtml(state.fetched_at)}</p>
    </div>
    <p class="muted">This app is for your own account only. Course materials stay on Blackboard; do not republish them.</p>
    <h2 style="font-size:20px">Font</h2>
    <div class="card">
      <p class="muted">The typeface used for the window. These are the readable faces already installed with Windows.</p>
      <select id="ui-font">
        ${UI_FONT_LABELS.map(([id, label]) => `<option value="${id}" ${id === (state.ui_font || "segoe") ? "selected" : ""}>${label}</option>`).join("")}
      </select>
    </div>
    <h2 style="font-size:20px">Opening pages</h2>
    <div class="card">
      <p class="muted">Choose where Open sends a Blackboard page. If Chrome or Edge cannot start, WhiteBoard opens the page in its own window.</p>
      <select id="page-opener">
        ${PAGE_OPENERS.map(([id, label]) => `<option value="${id}" ${id === (state.page_opener || "builtin") ? "selected" : ""}>${label}</option>`).join("")}
      </select>
    </div>
    <h2 style="font-size:20px">Lists</h2>
    <div class="card">
      <p class="muted">How many items to show at once on assignments, grades, the calendar, course pages, and Contents.</p>
      <select id="page-size">
        ${[10, 20, 50].map((size) => `<option value="${size}" ${size === pageSize ? "selected" : ""}>Show ${size} at once</option>`).join("")}
      </select>
      <p style="color:${pageSize > 20 ? "var(--warn)" : "var(--muted)"};font-weight:${pageSize > 20 ? 600 : 400}">More than 20 items on one page can make the app lag.</p>
    </div>
    <h2 style="font-size:20px">Colors</h2>
    <div class="card"><p class="muted">Borders show how close a deadline is. Fills show which course an item belongs to.</p>${swatches}
      <button class="text-btn" id="reset-deadline-colors">Reset deadline colors</button></div>
    <p class="muted">Pick a color for each course. Courses you leave alone keep an automatic color.</p>
    ${courseColors}
    ${state.courses.some((course) => course.custom) ? '<button class="text-btn" id="reset-course-colors">Reset course colors</button>' : ""}
    ${colorDialog ? colorModal() : ""}
    <h2 style="font-size:20px">Google Calendar</h2>
    <div class="card">
      <p class="muted">Sign in once. After each refresh, WhiteBoard updates a calendar named WhiteBoard. Finished work is removed. Google has to be reachable from this computer.</p>
      <label class="row"><input id="google-sync-enabled" type="checkbox" ${google.sync_enabled ? "checked" : ""}/> Update the WhiteBoard calendar after each refresh</label>
      <div class="row">
        <button class="fill-btn" id="google-signin" ${state.google_busy ? "disabled" : ""}>Sign in to Google</button>
        <button class="outline-btn" id="google-sync" ${state.google_busy || !signed ? "disabled" : ""}>Sync now</button>
        <button class="text-btn" id="google-signout" ${!signed || state.google_busy ? "disabled" : ""}>Sign out</button>
      </div>
      <p class="muted">${escapeHtml(who)}</p>
      ${google.status ? `<p class="muted">${escapeHtml(google.status)}</p>` : ""}
    </div>`;
}

function assignCard(item, withActions) {
  const dest = item.assignment_id || item.id;
  const submitted = item.status === "submitted" || !!item.finished;
  const extra = [item.kind === "other" ? "event" : "", submitted || item.finished ? "dimmed" : ""].filter(Boolean).join(" ");
  const kind = item.manual ? "Done locally" : submitted ? "Submitted on Blackboard" : item.kind || item.status || "";
  const background = submitted ? "#e2e8f0" : (item.kind === "other" ? "" : item.fill);
  const check = withActions && selectMode
    ? `<input class="assign-check" type="checkbox" data-assign-select="${escapeAttr(item.id)}" ${selectedAssignments.has(item.id) ? "checked" : ""} />`
    : "";
  const open = item.url
    ? actionButton(`data-open="${escapeAttr(item.url)}" data-title="${escapeAttr(item.title || "")}" data-id="${escapeAttr(item.id || "")}"`, "Open", "open")
    : "";
  let actions = "";
  if (withActions && route === "/ignored") {
    actions = `${open}${actionButton(`data-assign-restore="${escapeAttr(item.id)}"`, "Restore", "restore")}`;
  } else if (withActions && item.kind !== "other") {
    const mark = submitted
      ? (item.manual ? actionButton(`data-assign-undo="${escapeAttr(item.id)}"`, "Undo", "undo") : "")
      : actionButton(`data-assign-mark="${escapeAttr(item.id)}"`, "Mark done in WhiteBoard", "submitted", "mark-btn");
    actions = `${mark}${open}${actionButton(`data-assign-ignore="${escapeAttr(item.id)}"`, "Ignore", "ignore")}`;
  }
  const timing = submitted
    ? `<div class="countdown submitted" data-due="${item.ts || 0}" data-submitted="1" data-submitted-at="${item.submitted_ts || 0}">${escapeHtml(submittedTiming(item.ts || 0, item.submitted_ts || 0))}</div>`
    : `<div class="countdown" data-due="${item.ts || 0}" style="color:${item.border}">${escapeHtml(item.countdown || formatCountdown(item.ts || 0))}</div>`;
  return `<article class="assign ${extra}" style="border-color:${submitted ? "#94a3b8" : item.border};background:${background}" ${item.kind === "other" ? `data-open="${escapeAttr(item.url || "")}"` : `data-go="/assignments/${encodeURIComponent(dest)}"`}>
    <div class="assign-copy">
      ${check}
      <div class="assign-main"><strong>${escapeHtml(item.title)}</strong><div class="assign-when">${escapeHtml(item.when || "")} · ${escapeHtml(item.course || "")}</div></div>
    </div>
    <div class="assign-meta">
      ${timing}
      <span class="chip ${kind}">${escapeHtml(kind)}</span>
      <div class="row">${actions}</div>
    </div>
  </article>`;
}

function gradeCard(grade) {
  const button = grade.note ? `<button class="text-btn" data-feedback="${escapeAttr(grade.id)}">View feedback</button>` : "";
  return `<article class="card row" style="background:${grade.fill}">
    <div data-go="/courses/${encodeURIComponent(grade.course_id)}"><strong>${escapeHtml(grade.title)}</strong><div class="muted">${escapeHtml(grade.course)} · ${escapeHtml(grade.due)}</div></div>
    <span class="spacer"></span><div><strong>${escapeHtml(grade.label)}</strong>${button}</div>
  </article>`;
}

function folder(key, title, items, renderItem) {
  const open = openFolders[key];
  const body = open ? paged(key, items, renderItem) : "";
  return `<section class="folder"><button data-folder="${key}">${title} · ${items.length}</button><div class="body">${body}</div></section>`;
}

function paged(key, items, renderItem) {
  const size = pageSize;
  const page = Math.min(pages[key] || 0, Math.max(0, Math.ceil(items.length / size) - 1));
  pages[key] = page;
  const slice = items.slice(page * size, page * size + size);
  const cards = slice.map(renderItem).join("") || `<p class="muted">Nothing in this list.</p>`;
  return cards + pager(key, items.length, page, size);
}

function pager(key, total, page, size) {
  if (total <= size) return "";
  const start = page * size + 1;
  const end = Math.min(total, page * size + size);
  return `<div class="pager">
    <button class="outline-btn" data-page="${key}:-1" ${page === 0 ? "disabled" : ""}>Previous</button>
    <span class="muted">${start}–${end} of ${total}</span>
    <button class="outline-btn" data-page="${key}:1" ${end >= total ? "disabled" : ""}>Next</button>
  </div>`;
}

function searchBox(key, hint) {
  return `<input class="search" id="list-search" data-key="${key}" placeholder="${hint}" value="${escapeAttr(query[key] || "")}" />`;
}

function legend() {
  const colors = state.deadline_colors || {};
  const bits = [["overdue", "Overdue"], ["today", "Due today"], ["soon", "3 days"], ["week", "This week"], ["later", "Later"]]
    .map(([key, label]) => `<span class="row"><span class="swatch" style="border-color:${colors[key]}"></span>${label}</span>`).join("");
  return `<div class="legend"><span>Border: deadline</span>${bits}<span>Fill: course</span>
    <span class="row"><span class="swatch" style="border-color:var(--event);background:var(--event-bg)"></span>Event</span></div>`;
}

function errorBanners() {
  const labels = {
    harvest: "Could not read Ultra pages",
    profile: "Could not load your profile",
    calendar: "Couldn't load deadlines",
    grades: "Couldn't load grades",
    courses: "Couldn't load courses",
    refresh: "Refresh failed",
  };
  return Object.entries(labels).map(([key, label]) => {
    const text = (state.errors || {})[key];
    return text ? `<div class="banner">${escapeHtml(label)}: ${escapeHtml(text)}</div>` : "";
  }).join("");
}

function ringSvg(percent) {
  const radius = 30;
  const circ = 2 * Math.PI * radius;
  const target = circ * (1 - Math.max(0, Math.min(100, percent)) / 100);
  return `<svg class="ring" viewBox="0 0 76 76">
    <circle cx="38" cy="38" r="${radius}" fill="none" stroke="#e2e8f0" stroke-width="7"></circle>
    <circle class="value" data-ring="${target}" data-circ="${circ}" cx="38" cy="38" r="${radius}" fill="none" stroke="#2563eb" stroke-width="7"
      stroke-linecap="round" stroke-dasharray="${circ}" stroke-dashoffset="${circ}" transform="rotate(-90 38 38)"></circle>
    <text x="38" y="42" text-anchor="middle" font-size="13" font-weight="700" fill="#0f172a">${Math.round(percent)}%</text>
  </svg>`;
}

function animateMeters() {
  requestAnimationFrame(() => {
    document.querySelectorAll("[data-bar]").forEach((bar) => {
      bar.style.width = `${bar.dataset.bar}%`;
    });
    document.querySelectorAll("[data-ring]").forEach((ring) => {
      ring.style.strokeDashoffset = ring.dataset.ring;
    });
  });
}

function feedbackModal() {
  return `<div class="modal-back"><div class="modal">
    <h3>${escapeHtml(feedback.title)}</h3>
    <p class="muted">${escapeHtml(feedback.course)}</p>
    <p><strong>${escapeHtml(feedback.label)}</strong></p>
    <p>${escapeHtml(feedback.note)}</p>
    <button class="outline-btn" id="close-feedback">Close</button>
  </div></div>`;
}

function viewerView() {
  return `<div class="viewer">
    <div class="chrome">
      <button class="outline-btn" id="viewer-back">Back</button>
      <div class="url">${escapeHtml(viewer)}</div>
      <button class="fill-btn pill" id="viewer-home">WhiteBoard</button>
    </div>
    <iframe src="${escapeAttr(viewer)}" style="flex:1;border:0"></iframe>
  </div>`;
}

async function openUrl(url, title, id) {
  if (!url && !id) return;
  try {
    const result = await api("/api/open", { url: url || "", title: title || "", id: id || "" });
    if (result && result.fallback && result.message) {
      contentsNote = result.message;
      const note = document.getElementById("contents-note");
      if (note) note.textContent = contentsNote;
    }
  } catch (error) {
    contentsNote = (error && error.message) || "Could not open that page.";
    const note = document.getElementById("contents-note");
    if (note) note.textContent = contentsNote;
  }
}

function showDownloadProgress(message) {
  const banner = document.getElementById("download-banner");
  if (!banner) return;
  banner.hidden = false;
  const id = message.id || "main";
  let row = banner.querySelector(`[data-progress="${CSS.escape(id)}"]`);
  if (!row) {
    row = document.createElement("div");
    row.dataset.progress = id;
    row.className = "download-row";
    row.innerHTML = `<div class="zip-label"></div><div class="load-track"><span></span></div><button id="cancel-download" class="text-btn">Cancel download</button>`;
    banner.appendChild(row);
  }
  const label = row.querySelector(".zip-label");
  const fill = row.querySelector("span");
  const percent = Math.max(0, Math.min(100, Math.round((message.percent || 0) * 100)));
  const phase = message.phase || "Downloading";
  if (label) label.textContent = message.done ? `${message.name || "Download"} finished.` : `${phase} ${message.name || "files"}…`;
  if (fill) fill.style.width = `${Math.max(percent, 4)}%`;
  if (message.done) {
    setTimeout(() => {
      row.remove();
      if (!banner.querySelector("[data-progress]")) banner.hidden = true;
    }, 1600);
  }
}

async function downloadSelected() {
  const ids = [...contentsSelected];
  const folders = [...contentsFolders];
  if (!ids.length && !folders.length) return;
  contentsNote = "Downloading…";
  const note = document.getElementById("contents-note");
  if (note) note.textContent = contentsNote;
  showDownloadProgress({ name: "files", percent: 0.02, done: false });
  const button = document.getElementById("contents-download");
  if (button) button.disabled = true;
  try {
    const result = await api("/api/download", { ids, folders });
    contentsNote = (result && result.message) || "Download finished.";
  } catch (error) {
    contentsNote = (error && error.message) || "Download failed.";
  }
  if (note) note.textContent = contentsNote;
  if (button) button.disabled = contentsSelected.size === 0;
}

function topOf(path) {
  if (path.startsWith("/courses")) return "/home";
  if (path.startsWith("/assignments")) return "/assignments";
  return path;
}

function actionButton(attrs, label, icon, extraClass) {
  const cls = extraClass ? ` ${extraClass}` : "";
  return `<button class="outline-btn with-icon${cls}" type="button" title="${escapeAttr(label)}" ${attrs}>${actionIcon(icon)}<span>${label}</span></button>`;
}

function actionIcon(name) {
  const icons = {
    open: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M8 5H5v14h14v-3"/><path d="M11 13 19 5"/><path d="M13 5h6v6"/></svg>`,
    submitted: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="8"/><path d="M8.5 12.2 11 14.7 15.8 9.5"/></svg>`,
    ignore: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 5l18 14M10.5 10.7A3 3 0 0 0 13.3 13.5M9.9 6.1A10 10 0 0 1 12 5.8c5 0 8.5 4.2 9.4 5.4a1.3 1.3 0 0 1 0 1.6 12 12 0 0 1-3.2 3.1M6.2 8.3A12 12 0 0 0 2.6 12.8a1.3 1.3 0 0 0 0 1.6C3.5 15.6 7 19.8 12 19.8c1.2 0 2.3-.2 3.4-.6"/></svg>`,
    undo: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M8 7H4v4"/><path d="M5 10a7 7 0 1 1-1 4"/></svg>`,
    restore: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M2.5 12S6 6.8 12 6.8 21.5 12 21.5 12 18 17.2 12 17.2 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.4"/></svg>`,
  };
  return icons[name] || "";
}

function navIcon(name) {
  const icons = {
    home: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 10.5 12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1z"/></svg>`,
    assignment: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="6" y="3.5" width="12" height="17" rx="2"/><path d="M9 3.5h6v3H9zM8 11h8M8 15h6"/></svg>`,
    "turned-in": `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="6" y="3.5" width="12" height="17" rx="2"/><path d="M9 3.5h6v3H9zM8.5 13.2l2.2 2.2 4.8-4.8"/></svg>`,
    hidden: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M3 5l18 14M10.5 10.7A3 3 0 0 0 13.3 13.5M9.9 6.1A10 10 0 0 1 12 5.8c5 0 8.5 4.2 9.4 5.4a1.3 1.3 0 0 1 0 1.6 12 12 0 0 1-3.2 3.1M6.2 8.3A12 12 0 0 0 2.6 12.8a1.3 1.3 0 0 0 0 1.6C3.5 15.6 7 19.8 12 19.8c1.2 0 2.3-.2 3.4-.6"/></svg>`,
    grade: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="m12 3.8 2.3 4.7 5.2.8-3.8 3.6.9 5.2L12 15.7 7.4 18.1l.9-5.2-3.8-3.6 5.2-.8z"/></svg>`,
    folder: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 7.5h6l2 2H20v9.2a1.3 1.3 0 0 1-1.3 1.3H5.3A1.3 1.3 0 0 1 4 18.7z"/></svg>`,
    calendar: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="4" y="5" width="16" height="15" rx="2"/><path d="M8 3.5v3M16 3.5v3M4 10h16"/></svg>`,
    settings: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><circle cx="12" cy="12" r="3"/><path d="M19.4 13a7.8 7.8 0 0 0 .1-2l2-1.2-2-3.4-2.2.6a8 8 0 0 0-1.7-1L15.2 3h-6.4l-.4 2.8a8 8 0 0 0-1.7 1L4.5 6.4l-2 3.4 2 1.2a7.8 7.8 0 0 0 0 2l-2 1.2 2 3.4 2.2-.6a8 8 0 0 0 1.7 1l.4 2.8h6.4l.4-2.8a8 8 0 0 0 1.7-1l2.2.6 2-3.4z"/></svg>`,
  };
  return icons[name] || "";
}

function folderSvg(open) {
  return open
    ? `<svg class="file-icon folder" viewBox="0 0 24 24" fill="currentColor"><path d="M3 7h6l2 2h10v10H3z"/></svg>`
    : `<svg class="file-icon folder" viewBox="0 0 24 24" fill="currentColor"><path d="M3 6h7l2 2h9v11H3z"/></svg>`;
}

function fileTypeClass(node) {
  const ext = String((node && node.extension) || "").replace(/^\./, "").toLowerCase();
  const name = String((node && node.name) || "").toLowerCase();
  const kind = ext || (name.includes(".") ? name.split(".").pop() : "");
  if (kind === "ppt" || kind === "pptx") return "type-ppt";
  if (kind === "pdf") return "type-pdf";
  if (kind === "doc" || kind === "docx") return "type-word";
  if (kind === "xls" || kind === "xlsx" || kind === "csv") return "type-excel";
  if (kind === "mp3") return "type-audio";
  if (kind === "mp4" || kind === "m4v") return "type-video";
  return "type-other";
}

function fileSvg(node) {
  const type = fileTypeClass(node);
  const common = `class="file-icon ${type}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"`;
  if (type === "type-ppt") {
    return `<svg ${common}><rect x="4" y="5" width="16" height="12" rx="1.5"/><path d="M8 17v2h8v-2M10 9h4M10 12h3"/></svg>`;
  }
  if (type === "type-pdf") {
    return `<svg ${common}><path d="M7 3.5h7l5 5V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5A1 1 0 0 1 7 3.5z"/><path d="M14 3.5V9h5M8 14h2.2a1.4 1.4 0 0 0 0-2.8H8V16"/></svg>`;
  }
  if (type === "type-word") {
    return `<svg ${common}><path d="M7 3.5h7l5 5V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5A1 1 0 0 1 7 3.5z"/><path d="M14 3.5V9h5M8 13h8M8 16h6"/></svg>`;
  }
  if (type === "type-excel") {
    return `<svg ${common}><rect x="4" y="4" width="16" height="16" rx="1.5"/><path d="M4 10h16M4 15h16M10 4v16M15 4v16"/></svg>`;
  }
  if (type === "type-audio") {
    return `<svg ${common}><path d="M9 17a2.5 2.5 0 1 1-2-2.45V6.5l10-2v8.2"/><circle cx="17" cy="13.5" r="2.5"/></svg>`;
  }
  if (type === "type-video") {
    return `<svg ${common}><rect x="3" y="6" width="13" height="12" rx="1.5"/><path d="M16 10.5 21 8v8l-5-2.5z"/></svg>`;
  }
  return `<svg ${common}><path d="M7 3.5h7l5 5V20a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4.5A1 1 0 0 1 7 3.5z"/><path d="M14 3.5V9h5"/></svg>`;
}

function openSvg() {
  return `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M14 5h5v5M19 5l-8 8"/><path d="M11 6H6a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1v-5"/></svg>`;
}

function openColorDialog(title, current, onPick) {
  colorDialog = { title, current: current || "#2563eb", onPick };
  paintPage();
}

function colorModal() {
  const current = colorDialog.current || "#2563eb";
  const picks = SWATCHES.map((color) =>
    `<button class="swatch-pick ${color === current ? "current" : ""}" data-swatch="${color}" style="background:${color}" title="${color}"></button>`
  ).join("");
  return `<div class="modal-back"><div class="modal">
    <h3>${escapeHtml(colorDialog.title)}</h3>
    <p class="muted">Choose a swatch, or type a hex color.</p>
    <div class="row">${picks}</div>
    <label>Hex color</label>
    <input id="color-hex" type="text" value="${escapeAttr(current)}" />
    <div class="row" style="margin-top:12px">
      <button class="text-btn" id="color-cancel">Cancel</button>
      <button class="fill-btn" id="color-apply">Use this color</button>
    </div>
  </div></div>`;
}

function submittedTiming(dueTs, submittedTs) {
  const since = dueTs ? `${formatSpan(Math.abs(dueTs - Date.now() / 1000))} ${Date.now() / 1000 >= dueTs ? "since the deadline" : "until the deadline"}` : "";
  let submitted = "Submitted";
  if (submittedTs) {
    submitted = `Submitted ${new Date(submittedTs * 1000).toLocaleString("en-GB", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`;
  }
  return since ? `${submitted}\n${since}` : submitted;
}

function formatSpan(seconds) {
  seconds = Math.max(0, Math.trunc(seconds));
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  const clock = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  return days ? `${days}d ${clock}` : clock;
}

function formatCountdown(ts) {
  if (!ts) return "";
  let seconds = Math.trunc(ts - Date.now() / 1000);
  const overdue = seconds < 0;
  seconds = Math.abs(seconds);
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;
  const clock = `${String(hours).padStart(2, "0")}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  const body = days ? `${days}d ${clock}` : clock;
  return overdue ? `Overdue ${body}` : `Due in ${body}`;
}

function colorForDue(ts) {
  if (!ts) return "#94a3b8";
  const hours = (ts - Date.now() / 1000) / 3600;
  const colors = state && state.deadline_colors || {};
  if (hours < 0) return colors.overdue || "#9f1239";
  if (hours <= 24) return colors.today || "#ea580c";
  if (hours <= 72) return colors.soon || "#eab308";
  if (hours <= 168) return colors.week || "#22c55e";
  return colors.later || "#2563eb";
}

function tickCountdowns() {
  if (document.hidden) return;
  const nodes = document.querySelectorAll(".countdown[data-due]");
  if (!nodes.length) return;
  nodes.forEach((node) => {
    const ts = Number(node.dataset.due || 0);
    if (!ts) return;
    if (node.dataset.submitted === "1") {
      const text = submittedTiming(ts, Number(node.dataset.submittedAt || 0));
      if (node.textContent !== text) node.textContent = text;
      return;
    }
    const text = formatCountdown(ts);
    if (node.textContent !== text) node.textContent = text;
    const band = colorForDue(ts);
    if (node.dataset.band === band) return;
    node.dataset.band = band;
    node.style.color = band;
    const card = node.closest(".assign");
    if (card && !card.classList.contains("event") && !card.classList.contains("dimmed")) {
      card.style.borderColor = band;
    }
  });
}

function startOfDay(value) {
  return new Date(value.getFullYear(), value.getMonth(), value.getDate());
}

function weekStart(value) {
  const day = startOfDay(value);
  const delta = (day.getDay() + 6) % 7;
  return addDays(day, -delta);
}

function addDays(value, amount) {
  const next = new Date(value);
  next.setDate(next.getDate() + amount);
  return startOfDay(next);
}

function addMonths(value, amount) {
  return new Date(value.getFullYear(), value.getMonth() + amount, 1);
}

function isoDate(value) {
  const month = `${value.getMonth() + 1}`.padStart(2, "0");
  const day = `${value.getDate()}`.padStart(2, "0");
  return `${value.getFullYear()}-${month}-${day}`;
}

function decodeText(value) {
  let text = String(value ?? "");
  for (let pass = 0; pass < 3; pass += 1) {
    const next = text
      .replace(/&amp;/g, "&")
      .replace(/&quot;/g, '"')
      .replace(/&#34;/g, '"')
      .replace(/&apos;/g, "'")
      .replace(/&#39;/g, "'")
      .replace(/&lt;/g, "<")
      .replace(/&gt;/g, ">");
    if (next === text) break;
    text = next;
  }
  return text;
}

function escapeHtml(value) {
  return decodeText(value).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
function escapeAttr(value) { return escapeHtml(value); }

boot();

function showError(error) { jobError = error.message || String(error); render(); }

async function signOut() {
  const keep = window.confirm("Keep an offline copy of this account on this computer? Cancel signs out and removes the saved dashboard.");
  try {
    await api("/api/logout", { keep_offline: keep });
    manualMarks.clear(); contentsSelected.clear(); selectedAssignments.clear();
    query = {assignments:"", grades:"", courses:"", contents:""}; pages = {};
    await loadState(); go("/login"); render();
  } catch (error) { showError(error); }
}

async function ensureLazyContent() {
  if (!state || state.content_loaded || lazyRequests.has("content")) return;
  lazyRequests.add("content");
  const revision = state.revision;
  try {
    const result = await api("/api/content");
    if (state.revision === revision) { Object.assign(state,result); contentIndex=null; if (route === "/contents") paintContentsRoot(); }
  } catch (error) { showError(error); }
  finally { lazyRequests.delete("content"); }
}
async function ensureLazyCourse(id) {
  if (state.course_pages[id] || lazyRequests.has(id)) return;
  lazyRequests.add(id);
  const revision = state.revision;
  try {
    const result=await api("/api/course",{id});
    if (state.revision === revision) { Object.assign(state.course_pages,result.course_pages); if (route.startsWith("/courses/")) paintPage(); }
  } catch(error) { showError(error); }
  finally { lazyRequests.delete(id); }
}
