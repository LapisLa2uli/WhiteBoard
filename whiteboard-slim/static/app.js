let state = null;
let route = location.hash.slice(1) || "/home";
let pageSize = 10;
let pages = {};
let query = { assignments: "", grades: "", courses: "" };
let openFolders = { todo: true, submitted: false, graded: true, pending: true };
let hideEvents = false;
let busy = false;
let feedback = null;
let viewer = null;

async function loadState() {
  const response = await fetch("/api/state");
  state = await response.json();
  pageSize = state.page_size || 10;
  hideEvents = !!state.hide_calendar_events;
  if (!state.has_snapshot && route !== "/login") route = "/login";
}

async function boot() {
  await loadState();
  render();
  window.addEventListener("hashchange", () => {
    route = location.hash.slice(1) || "/home";
    render();
  });
}

function go(path) {
  location.hash = path;
}

function render() {
  const app = document.getElementById("app");
  if (!state || route === "/login" || !state.has_snapshot) {
    app.innerHTML = loginView();
    bindLogin();
    return;
  }
  if (viewer) {
    app.innerHTML = viewerView();
    bindViewer();
    return;
  }
  app.innerHTML = shell(viewFor(route));
  bindShell();
  animateMeters();
  if (feedback) bindFeedback();
}

function loginView() {
  return `<div class="login"><form class="card" id="login-form">
    <div class="row"><img src="/logo.png" width="48" height="48" alt="" /><h2>WhiteBoard</h2></div>
    <p class="muted">Sign in to Blackboard. A saved dashboard can be opened without signing in again.</p>
    <label>Username</label><input type="text" id="user" />
    <label>Password</label><input type="password" id="pass" />
    <div class="row" style="margin-top:14px">
      <button class="fill-btn" type="submit">Sign in</button>
      ${state && state.has_snapshot ? '<button class="outline-btn" type="button" id="saved">Open saved dashboard</button>' : ""}
    </div>
    <p class="muted" id="login-note"></p>
  </form></div>`;
}

function bindLogin() {
  const form = document.getElementById("login-form");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    document.getElementById("login-note").textContent =
      "Live sign-in uses the current WhiteBoard app. Open the saved dashboard to use this slim version.";
  });
  const saved = document.getElementById("saved");
  if (saved) saved.onclick = () => go("/home");
}

function shell(body) {
  const nav = [
    ["/home", "Home"], ["/assignments", "Assignments"], ["/submitted", "Submitted"],
    ["/ignored", "Ignored"], ["/grades", "Grades"], ["/contents", "Contents"],
    ["/calendar", "Calendar"], ["/settings", "Settings"],
  ].map(([path, label]) => {
    const active = topOf(route) === path ? "active" : "";
    return `<button class="nav-btn ${active}" data-go="${path}">${label}</button>`;
  }).join("");
  const courses = state.courses.filter((course) =>
    course.name.toLowerCase().includes(query.courses.toLowerCase())
  ).map((course) => `<button class="course-link ${route.endsWith(course.id) ? "active" : ""}" data-go="/courses/${encodeURIComponent(course.id)}" style="background:${course.fill};color:${course.ink}">${escapeHtml(course.name)}</button>`).join("");
  return `<div class="app">
    <aside class="sidebar">
      <h1><img src="/logo.png" alt="" /> Courses</h1>
      <input id="course-q" placeholder="Search courses" value="${escapeAttr(query.courses)}" />
      <div class="course-list">${courses || '<p class="muted">No courses</p>'}</div>
    </aside>
    <div class="main">
      <header class="topbar">
        <img src="/logo.png" alt="" />
        ${nav}
        <span class="spacer"></span>
        <span class="muted">${escapeHtml(state.fetched_at)}</span>
        <span class="muted">${escapeHtml(state.user_name || "")}</span>
        ${busy ? '<span class="ring" style="width:18px;height:18px">…</span>' : ""}
        <button class="outline-btn" id="refresh">Refresh</button>
        <button class="text-btn" id="logout">Log out</button>
      </header>
      ${busy ? '<div class="busy-bar"><span></span></div>' : ""}
      <div class="content">${body}</div>
    </div>
  </div>`;
}

function bindShell() {
  document.querySelectorAll("[data-go]").forEach((button) => {
    button.onclick = () => go(button.getAttribute("data-go"));
  });
  const courseQ = document.getElementById("course-q");
  if (courseQ) courseQ.oninput = () => { query.courses = courseQ.value; render(); courseQ.focus(); };
  document.getElementById("refresh").onclick = async () => {
    busy = true; render();
    await new Promise((resolve) => setTimeout(resolve, 700));
    await loadState();
    busy = false;
    render();
  };
  document.getElementById("logout").onclick = () => go("/login");
  const search = document.getElementById("list-search");
  if (search) {
    search.oninput = () => {
      const key = search.dataset.key;
      query[key] = search.value;
      pages[key] = 0;
      render();
      const again = document.getElementById("list-search");
      if (again) { again.focus(); again.setSelectionRange(again.value.length, again.value.length); }
    };
  }
  document.querySelectorAll("[data-folder]").forEach((button) => {
    button.onclick = () => {
      const key = button.dataset.folder;
      openFolders[key] = !openFolders[key];
      render();
    };
  });
  document.querySelectorAll("[data-page]").forEach((button) => {
    button.onclick = () => {
      const [key, delta] = button.dataset.page.split(":");
      pages[key] = Math.max(0, (pages[key] || 0) + Number(delta));
      render();
    };
  });
  document.querySelectorAll("[data-open]").forEach((node) => {
    node.onclick = () => openUrl(node.dataset.open);
  });
  document.querySelectorAll("[data-feedback]").forEach((button) => {
    button.onclick = (event) => {
      event.stopPropagation();
      const grade = [...state.graded, ...state.pending].find((item) => item.id === button.dataset.feedback);
      feedback = grade || null;
      render();
    };
  });
  const size = document.getElementById("page-size");
  if (size) size.onchange = () => { pageSize = Number(size.value); pages = {}; render(); };
  const hide = document.getElementById("hide-events");
  if (hide) hide.onchange = () => { hideEvents = hide.checked; render(); };
  const close = document.getElementById("close-feedback");
  if (close) close.onclick = () => { feedback = null; render(); };
}

function viewFor(path) {
  if (path.startsWith("/courses/")) return courseView(decodeURIComponent(path.slice("/courses/".length)));
  if (path.startsWith("/assignments/")) return assignmentView(decodeURIComponent(path.slice("/assignments/".length)));
  if (path === "/assignments") return assignmentList("all");
  if (path === "/submitted") return assignmentList("submitted");
  if (path === "/ignored") return `<h2>Ignored</h2><p class="muted">No ignored assignments in the saved dashboard.</p>`;
  if (path === "/grades") return gradesView();
  if (path === "/calendar") return calendarView();
  if (path === "/contents") return contentsView();
  if (path === "/settings") return settingsView();
  return homeView();
}

function homeView() {
  const due = state.home_due.map(assignCard).join("") || `<p class="muted">No deadlines this week.</p>`;
  const grades = state.home_grades.map((grade) => `<div class="card row" data-go="${grade.assignment_id ? "/assignments/" + encodeURIComponent(grade.assignment_id) : "/courses/" + encodeURIComponent(grade.course_id)}"><div><strong>${escapeHtml(grade.title)}</strong><div class="muted">${escapeHtml(grade.course)}</div></div><span class="spacer"></span><strong>${escapeHtml(grade.label)}</strong></div>`).join("") || `<p class="muted">No new grades.</p>`;
  return `<h2>Home</h2><p class="muted">This week at a glance.</p>
    <h3>Upcoming this week</h3>${legend()}${due}
    <h3>Recent grades</h3>${grades}`;
}

function assignmentList(mode) {
  const needle = query.assignments.toLowerCase();
  let items = state.assignments.filter((item) =>
    `${item.title} ${item.course}`.toLowerCase().includes(needle)
  );
  if (mode === "submitted") items = items.filter((item) => item.status === "submitted");
  const title = mode === "submitted" ? "Submitted" : "Assignments";
  if (mode === "submitted") {
    return `<h2>${title}</h2>${searchBox("assignments", "Search assignments")}${paged("assignments-submitted", items, assignCard)}`;
  }
  const todo = items.filter((item) => item.status !== "submitted");
  const done = items.filter((item) => item.status === "submitted");
  return `<h2>Assignments</h2>${searchBox("assignments", "Search assignments")}
    ${folder("todo", "To do", todo, assignCard)}
    ${folder("submitted", "Submitted", done, assignCard)}`;
}

function assignmentView(id) {
  const item = state.assignments.find((row) => row.id === id);
  if (!item) return `<h2>Assignment</h2><p class="muted">Not in the saved dashboard.</p>`;
  return `<button class="text-btn" data-go="/assignments">Back</button>
    <h2>${escapeHtml(item.title)}</h2>
    ${assignCard(item)}
    ${item.description ? `<div class="card"><p class="muted">Description</p><p>${escapeHtml(item.description)}</p></div>` : ""}
    <button class="outline-btn" data-open="${escapeAttr(item.url)}">Open</button>`;
}

function gradesView() {
  const needle = query.grades.toLowerCase();
  const match = (grade) => `${grade.title} ${grade.course} ${grade.label} ${grade.note}`.toLowerCase().includes(needle);
  const lines = state.score_lines.map((line) => `<div style="margin:12px 0">
      <div class="row"><span class="swatch" style="border-color:${line.ink};background:${line.fill}"></span><strong>${escapeHtml(line.name)}</strong><span class="spacer"></span><span>${line.percent}%</span></div>
      <div class="bar"><span data-bar="${line.percent}" style="background:${line.ink}"></span></div>
    </div>`).join("");
  return `<h2>Grades</h2><p class="muted">Posted scores and submitted work waiting for a grade.</p>
    ${searchBox("grades", "Search grades")}
    ${lines}
    ${folder("graded", "Graded", state.graded.filter(match), gradeCard)}
    ${folder("pending", "Submitted, not graded", state.pending.filter(match), gradeCard)}
    ${feedback ? feedbackModal() : ""}`;
}

function courseView(id) {
  const course = state.courses.find((item) => item.id === id);
  const page = (state.course_pages || {})[id];
  if (!course || !page) return `<h2>Course</h2><p class="muted">No course data.</p>`;
  const ring = page.percent == null ? "" : `<div>${ringSvg(page.percent)}<div class="muted" style="text-align:center">${escapeHtml(page.fraction)}</div></div>`;
  const upcoming = page.upcoming.map(assignCard).join("") || `<p class="muted">No upcoming work for this course.</p>`;
  const grades = page.grades.map((row) => `<div class="card row"><div><strong>${escapeHtml(row.title)}</strong><div class="muted">${escapeHtml(row.due)}</div></div><span class="spacer"></span><strong>${escapeHtml(row.label)}</strong></div>`).join("") || `<p class="muted">No grades for this course yet.</p>`;
  return `<div class="score-row"><h2>${escapeHtml(course.name)}</h2>${ring}</div>
    <h3>Upcoming work</h3>${upcoming}<h3>Grades</h3>${grades}`;
}

function calendarView() {
  const items = state.calendar.filter((item) => !hideEvents || item.kind !== "other");
  let last = "";
  const blocks = items.map((item) => {
    const head = item.day_label !== last ? `<h3>${escapeHtml(item.day_label)}</h3>` : "";
    last = item.day_label;
    return head + assignCard(item);
  }).join("") || `<p class="muted">No events.</p>`;
  return `<h2>Calendar</h2>
    <label class="row"><input id="hide-events" type="checkbox" ${hideEvents ? "checked" : ""}/> Hide events</label>
    ${legend()}${blocks}`;
}

function contentsView() {
  return `<h2>Contents</h2><p class="muted">Course files. ${state.content_count} indexed.</p>
    <p class="muted">${state.content_count ? "Open a course folder from the sidebar." : "Course files load when you open this page in the full app, or after Refresh."}</p>`;
}

function settingsView() {
  const colors = state.deadline_colors || {};
  const swatches = Object.entries({ overdue: "Overdue", today: "Due today", soon: "Within 3 days", week: "This week", later: "Later" })
    .map(([key, label]) => `<div class="row"><span class="swatch" style="border-color:${colors[key]}"></span><span>${label}</span><span class="muted">${colors[key] || ""}</span></div>`).join("");
  return `<h2>Settings</h2>
    <div class="card"><h3>Lists</h3>
      <p class="muted">How many items to show at once.</p>
      <select id="page-size">
        ${[10, 20, 50].map((size) => `<option ${size === pageSize ? "selected" : ""}>${size}</option>`).join("")}
      </select>
      <p style="color:${pageSize > 20 ? "var(--warn)" : "var(--muted)"}">More than 20 items on one page can make the app lag.</p>
    </div>
    <div class="card"><h3>Colors</h3><p class="muted">Borders show how close a deadline is. Fills show the course.</p>${swatches}</div>
    <div class="card"><h3>Google Calendar</h3><p class="muted">Sign-in and sync stay available from the full WhiteBoard app. This slim view reads the same saved dashboard.</p></div>`;
}

function assignCard(item) {
  const dest = item.assignment_id || item.id;
  return `<article class="assign" style="border-color:${item.border};background:${item.fill}" data-go="/assignments/${encodeURIComponent(dest)}">
    <div><strong>${escapeHtml(item.title)}</strong><div class="muted">${escapeHtml(item.when || "")} · ${escapeHtml(item.course || "")}</div></div>
    <div><div class="countdown" style="color:${item.border}">${escapeHtml(item.countdown || "")}</div><span class="chip ${item.kind || ""}">${escapeHtml(item.kind || item.status || "")}</span></div>
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
  if (items.length <= size) return cards;
  const start = page * size + 1;
  const end = Math.min(items.length, page * size + size);
  return `${cards}<div class="pager">
    <button class="outline-btn" data-page="${key}:-1" ${page === 0 ? "disabled" : ""}>Previous</button>
    <span class="muted">${start}–${end} of ${items.length}</span>
    <button class="outline-btn" data-page="${key}:1" ${end >= items.length ? "disabled" : ""}>Next</button>
  </div>`;
}

function searchBox(key, hint) {
  return `<input class="search" id="list-search" data-key="${key}" placeholder="${hint}" value="${escapeAttr(query[key] || "")}" />`;
}

function legend() {
  const colors = state.deadline_colors || {};
  const bits = [["overdue", "Overdue"], ["today", "Due today"], ["soon", "3 days"], ["week", "This week"], ["later", "Later"]]
    .map(([key, label]) => `<span class="row"><span class="swatch" style="border-color:${colors[key]}"></span>${label}</span>`).join("");
  return `<div class="legend"><span>Border: deadline</span>${bits}<span>Fill: course</span></div>`;
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
      <button class="fill-btn" id="viewer-home">WhiteBoard</button>
    </div>
    <iframe src="${escapeAttr(viewer)}" style="flex:1;border:0"></iframe>
  </div>`;
}

function bindViewer() {
  document.getElementById("viewer-home").onclick = () => { viewer = null; render(); };
  document.getElementById("viewer-back").onclick = () => { viewer = null; render(); };
}

async function openUrl(url) {
  if (!url) return;
  viewer = url;
  render();
  await fetch("/api/open", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) });
}

function topOf(path) {
  if (path.startsWith("/courses")) return "/home";
  if (path.startsWith("/assignments")) return "/assignments";
  return path;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
}
function escapeAttr(value) { return escapeHtml(value); }

boot();
