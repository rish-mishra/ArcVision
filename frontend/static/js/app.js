/* ArcVision -- frontend application logic. Vanilla JS, no build
   step: every value rendered here comes straight from the backend's JSON
   response -- this file only formats and lays it out. */

const STAGE_ORDER = [
  "validating_video", "analyzing_player_and_ball", "locating_hoop", "detecting_shots",
  "locating_ball_near_hoop", "analyzing_mechanics", "comparing_attempts", "finalizing", "rendering_replay",
];
const STAGE_LABELS = {
  validating_video: "Validating video", analyzing_player_and_ball: "Tracking player and basketball",
  locating_hoop: "Locating hoop", detecting_shots: "Detecting shot attempts",
  locating_ball_near_hoop: "Refining ball position near hoop",
  analyzing_mechanics: "Analyzing shooting mechanics", comparing_attempts: "Comparing makes vs. misses",
  finalizing: "Finalizing results", rendering_replay: "Generating annotated replay",
};

let currentResults = null;
let currentSessionId = null;
let pollTimer = null;
let elapsedTimer = null;

/* Tracks the one session this tab considers "active" -- still processing,
   or just finished and not yet opened -- so the topbar indicator and the
   History/navigation-survives-processing behavior have a single source of
   truth. Shape: { sessionId, createdAtMs, status, error }. Never more than
   one at a time: starting a new upload while one is active is refused
   (see handleFile below), so there's no ambiguity about which job the
   indicator refers to. */
let activeJob = null;

const ACTIVE_SESSION_KEY = "arcvision_active_session";
function persistActiveSession(sessionId) {
  try { localStorage.setItem(ACTIVE_SESSION_KEY, sessionId); } catch (e) { /* private browsing, etc. -- non-fatal */ }
}
function readPersistedActiveSession() {
  try { return localStorage.getItem(ACTIVE_SESSION_KEY); } catch (e) { return null; }
}
function clearPersistedActiveSession() {
  try { localStorage.removeItem(ACTIVE_SESSION_KEY); } catch (e) { /* non-fatal */ }
}

function formatElapsed(ms) {
  const totalSec = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return m > 0 ? `${m}m ${String(s).padStart(2, "0")}s` : `${s}s`;
}

/* ---------------- Active job indicator (topbar) ---------------- */

function updateActiveJobIndicator() {
  const el = document.getElementById("active-job-indicator");
  const text = document.getElementById("active-job-text");
  if (!el || !text) return;
  if (!activeJob) { el.style.display = "none"; return; }

  el.style.display = "flex";
  el.classList.remove("ready", "errored");
  if (activeJob.status === "processing" || activeJob.status === "queued") {
    text.textContent = `Analyzing session · ${formatElapsed(Date.now() - activeJob.createdAtMs)}`;
  } else if (activeJob.status === "completed") {
    el.classList.add("ready");
    text.textContent = "Analysis ready — click to view";
  } else {
    el.classList.add("errored");
    text.textContent = "Analysis failed — click for details";
  }
}

function startElapsedTicker() {
  if (elapsedTimer) clearInterval(elapsedTimer);
  elapsedTimer = setInterval(() => {
    if (!activeJob || (activeJob.status !== "processing" && activeJob.status !== "queued")) return;
    const elapsedEl = document.getElementById("elapsed-time");
    if (elapsedEl) {
      elapsedEl.textContent = `ArcVision is actively analyzing your video · ${formatElapsed(Date.now() - activeJob.createdAtMs)} elapsed`;
    }
    updateActiveJobIndicator();
  }, 1000);
}

async function openActiveJobResults() {
  if (!activeJob) return;
  try {
    const results = await Api.results(activeJob.sessionId);
    currentResults = results;
    renderDashboard(results);
    switchView("dashboard");
    activeJob = null;
    updateActiveJobIndicator();
  } catch (err) {
    showLandingError(err.message || "Could not load results.");
  }
}

function initActiveJobIndicator() {
  const el = document.getElementById("active-job-indicator");
  if (!el) return;
  el.addEventListener("click", () => {
    if (!activeJob) return;
    if (activeJob.status === "processing" || activeJob.status === "queued") {
      switchView("processing");
    } else if (activeJob.status === "completed") {
      openActiveJobResults();
    } else {
      showLandingError(activeJob.error || "Analysis failed.");
    }
  });
}

/* Re-attaches to an in-flight job after a page reload/reopen -- the
   backend keeps processing independently of any browser tab (it's a
   server-side worker thread, not driven by the frontend), so all this
   needs to do is rediscover which session was active and resume polling
   it. If it finished (or vanished) while this tab was closed, there's
   nothing to silently resume into -- History still has the full record. */
async function resumeActiveSessionIfAny() {
  if (window.ARCVISION_MODE === "demo") return; // no backend to poll in the static demo
  const sessionId = readPersistedActiveSession();
  if (!sessionId) return;
  try {
    const status = await Api.status(sessionId);
    if (status.status === "processing" || status.status === "queued") {
      const createdAtMs = Date.parse(status.created_at);
      activeJob = {
        sessionId, status: status.status,
        createdAtMs: Number.isNaN(createdAtMs) ? Date.now() : createdAtMs,
        error: null,
      };
      currentSessionId = sessionId;
      updateActiveJobIndicator();
      startElapsedTicker();
      switchView("processing");
      renderStageList(status.stage);
      document.getElementById("progress-fill").style.width = `${Math.round(status.progress * 100)}%`;
      beginPolling(sessionId);
    } else {
      clearPersistedActiveSession();
    }
  } catch (err) {
    clearPersistedActiveSession();
  }
}

/* Mirrors app/config.py::VideoConfig -- a best-effort, client-side PRE-check
   only, so an obviously-invalid file doesn't make a full upload round trip
   before finding out. The server (app/api/routes.py + validate_video) is
   still the sole authority: if these ever drift out of sync, the worst case
   is a slightly-off client hint, never a wrongly-accepted or wrongly-blocked
   upload. Keep in sync manually if VideoConfig changes. */
const VIDEO_LIMITS = {
  allowedExtensions: [".mp4", ".mov", ".m4v", ".avi"],
  maxFileSizeMb: 500,
  minDurationSec: 1.5,
  maxDurationSec: 300,
};

function switchView(name) {
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.getElementById(`view-${name}`).classList.add("active");
}

/* Nav links into landing-page sections ("How It Works", "Tech") need to work
   from inside the dashboard too, where the target section exists in the DOM
   but its ancestor .view is display:none -- a plain href="#id" anchor jump
   would silently do nothing there instead of taking the visitor back to the
   landing page. This switches to the landing view first (a no-op if already
   there) and only then scrolls, using rAF x2 to wait for the display:none ->
   block layout change to actually take effect before measuring scroll
   position (scrolling immediately after the class change can measure the
   pre-reflow, still-collapsed layout). */
function goToLandingSection(sectionId) {
  const alreadyOnLanding = document.getElementById("view-landing").classList.contains("active");
  if (!alreadyOnLanding) switchView("landing");
  const scrollToSection = () => {
    const el = document.getElementById(sectionId);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  };
  if (alreadyOnLanding) {
    scrollToSection();
  } else {
    requestAnimationFrame(() => requestAnimationFrame(scrollToSection));
  }
}

/* ---------------- Upload flow ---------------- */

/* Reads a video file's duration client-side via a throwaway <video> element.
   Best-effort and bounded by a timeout: some codecs won't preview cleanly in
   every browser, and a preview limitation must never block a legitimate
   upload -- on any failure/timeout this resolves to null and the caller
   simply skips the duration check, leaving the server as the fallback
   authority (exactly as it already is today). */
function readVideoDuration(file, timeoutMs = 5000) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    let settled = false;
    const finish = (duration) => {
      if (settled) return;
      settled = true;
      URL.revokeObjectURL(url);
      resolve(typeof duration === "number" && !Number.isNaN(duration) ? duration : null);
    };
    const timer = setTimeout(() => finish(null), timeoutMs);
    video.preload = "metadata";
    video.onloadedmetadata = () => { clearTimeout(timer); finish(video.duration); };
    video.onerror = () => { clearTimeout(timer); finish(null); };
    video.src = url;
  });
}

async function validateFileClientSide(file) {
  const name = file.name || "";
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot).toLowerCase() : "";
  if (!VIDEO_LIMITS.allowedExtensions.includes(ext)) {
    return {
      ok: false,
      message: `Unsupported file type "${ext || "unknown"}". Allowed: ${VIDEO_LIMITS.allowedExtensions.join(", ")}.`,
    };
  }
  const sizeMb = file.size / (1024 * 1024);
  if (sizeMb > VIDEO_LIMITS.maxFileSizeMb) {
    return { ok: false, message: `This file is ${sizeMb.toFixed(0)}MB, over the ${VIDEO_LIMITS.maxFileSizeMb}MB limit.` };
  }
  const durationSec = await readVideoDuration(file);
  if (durationSec !== null) {
    if (durationSec < VIDEO_LIMITS.minDurationSec) {
      return { ok: false, message: `This video is ${durationSec.toFixed(1)}s, shorter than the ${VIDEO_LIMITS.minDurationSec}s minimum.` };
    }
    if (durationSec > VIDEO_LIMITS.maxDurationSec) {
      return { ok: false, message: `This video is ${durationSec.toFixed(0)}s, longer than the ${VIDEO_LIMITS.maxDurationSec}s maximum.` };
    }
  }
  return { ok: true, durationSec };
}

function setProcessingExpectations(durationSec) {
  const el = document.getElementById("processing-expectation");
  if (!el) return;
  if (durationSec !== null && durationSec !== undefined) {
    el.textContent = `Your video is about ${Math.round(durationSec)}s long. Full analysis -- including the ` +
      `annotated replay -- commonly takes several times the video's own length, and can take 10+ minutes for ` +
      `longer clips. Keep this tab open.`;
  } else {
    el.textContent = `This can take several minutes. Longer videos (2+ minutes) can take 10+ minutes, ` +
      `especially while the annotated replay renders. Keep this tab open.`;
  }
}

/* ---------------- Demo mode ----------------
   Everything here is presentation only -- it decides how the UI explains
   itself when window.ARCVISION_MODE === "demo" (set by the exported static
   bundle, see frontend/static/js/env.js and scripts/export_demo.py). Local
   mode's real upload/History/processing flow is completely unaffected;
   these functions simply aren't reached when ARCVISION_MODE is "local". */

function renderDemoUploadNotice() {
  const notice = document.getElementById("demo-upload-notice");
  const actions = document.getElementById("demo-upload-actions");
  if (!notice) return;
  const repoUrl = window.ARCVISION_REPO_URL;
  actions.innerHTML = repoUrl
    ? `<a class="btn" href="${repoUrl}#windows-installation" target="_blank" rel="noopener">Run ArcVision locally</a>
       <a class="btn secondary" href="${repoUrl}" target="_blank" rel="noopener">View on GitHub</a>`
    : `<span class="demo-upload-actions-pending">See the project README for local installation instructions.</span>`;
  notice.style.display = "block";
}

function showDemoUploadNotice() {
  renderDemoUploadNotice();
  document.getElementById("demo-upload-notice").scrollIntoView({ behavior: "smooth", block: "nearest" });
}

function renderDemoBanner() {
  const el = document.getElementById("demo-banner");
  if (!el) return;
  if (window.ARCVISION_MODE !== "demo") { el.innerHTML = ""; return; }
  el.innerHTML = `
    <div class="demo-banner">
      <div class="demo-banner-eyebrow">Interactive demo &middot; Real ArcVision analysis</div>
      <p>This session was processed by ArcVision's actual RF-DETR detection and pose/biomechanics pipeline.
        The public demo shows precomputed results so it can be hosted for free without requiring a GPU &mdash;
        nothing here is fabricated or simulated. <a href="#" id="demo-run-own-link">Run ArcVision locally to
        analyze your own footage &rarr;</a></p>
    </div>`;
  const link = document.getElementById("demo-run-own-link");
  if (link) {
    link.addEventListener("click", (e) => {
      e.preventDefault();
      switchView("landing");
      showDemoUploadNotice();
    });
  }
}

function initDemoMode() {
  if (window.ARCVISION_MODE !== "demo") return;

  // Every landing-page section that only makes sense for the public demo
  // (nav links, the product-preview section, the proof strip) carries this
  // class and is display:none by default in main.css -- a single body
  // class flips all of them on at once instead of toggling each element's
  // inline style individually. Local mode never reaches this function, so
  // it never gains the class and these sections stay hidden there.
  document.body.classList.add("is-demo-mode");

  const cta = document.getElementById("demo-cta");
  if (cta) cta.style.display = "block";

  // The public demo can't process an arbitrary upload, so the real dropzone
  // (local mode's actual upload interaction, left entirely intact below in
  // initUpload()) never renders in demo mode -- this non-interactive card
  // takes its place instead of only appearing after a misleading drag/click.
  const dropzone = document.getElementById("dropzone");
  if (dropzone) dropzone.style.display = "none";
  renderDemoUploadNotice();

  // Nav "GitHub" and the proof strip's "full evaluation" link both point at
  // the public repository -- populated at runtime from the same env value
  // as renderDemoUploadNotice() above, never hardcoded (see
  // frontend/static/js/env.js). Left as "#" (inert) if the repo URL isn't
  // known yet, same graceful-degradation behavior as the rest of demo mode.
  // "Run ArcVision locally" now lives only in the hero's own secondary
  // action (populated by renderDemoUploadNotice()), not in the nav.
  const repoUrl = window.ARCVISION_REPO_URL;
  if (repoUrl) {
    const githubLink = document.getElementById("nav-github-link");
    if (githubLink) githubLink.href = repoUrl;
    const evalLink = document.getElementById("proof-eval-link");
    if (evalLink) evalLink.href = repoUrl;
  }

  // Neither claim is true for the static demo -- there's no backend to
  // build a session history against (a single precomputed session, not a
  // per-visitor library), and nothing is ever processed on this machine.
  // Local mode never reaches this function, so its own History tab and
  // privacy pill are completely unaffected.
  const navHistory = document.getElementById("nav-history");
  if (navHistory) navHistory.style.display = "none";
  const privacyPill = document.getElementById("privacy-pill");
  if (privacyPill) privacyPill.style.display = "none";

  // "No video leaves this machine" is a claim about local processing that
  // doesn't apply to a static, precomputed bundle -- swap in wording that's
  // accurate for the public demo. The "How this works" link/button right
  // after this span is untouched.
  const footerCopy = document.getElementById("footer-copy");
  if (footerCopy) {
    footerCopy.textContent = "ArcVision — computer-vision basketball shot analysis · Interactive demo uses real precomputed results";
  }

  // "Analyze another video" implies the hosted demo could process a
  // different upload -- it can't (there's only ever this one precomputed
  // session). Its click handler already branches on demo mode in
  // initUpload() to route here instead of a dropzone; this just relabels
  // it to match what it actually does now.
  const newSessionBtn = document.getElementById("new-session-btn");
  if (newSessionBtn) newSessionBtn.textContent = "Run ArcVision locally";

  async function enterInteractiveDemo() {
    try {
      const results = await Api.loadDemoSession();
      currentResults = results;
      renderDashboard(results);
      switchView("dashboard");
    } catch (err) {
      const errorBox = document.getElementById("upload-error");
      errorBox.textContent = err.message || "The demo session could not be loaded.";
      errorBox.style.display = "block";
    }
  }

  // Three "Try Interactive Demo"/"Try Demo" entry points on the redesigned
  // landing page (hero, product-preview section, nav) all load the exact
  // same precomputed session through the exact same call -- none of them
  // duplicate or reimplement demo-loading logic. The preview CTA keeps its
  // href="#demo-cta" in markup as a no-JS fallback (scrolls to the hero),
  // overridden here to actually open the demo when JS runs.
  const tryBtn = document.getElementById("try-demo-btn");
  if (tryBtn) tryBtn.addEventListener("click", enterInteractiveDemo);

  const previewTryBtn = document.getElementById("preview-demo-btn");
  if (previewTryBtn) {
    previewTryBtn.addEventListener("click", (e) => {
      e.preventDefault();
      enterInteractiveDemo();
    });
  }

  const navTryDemoBtn = document.getElementById("nav-try-demo-btn");
  if (navTryDemoBtn) navTryDemoBtn.addEventListener("click", enterInteractiveDemo);

  const heroFrameCta = document.getElementById("hero-frame-cta");
  if (heroFrameCta) heroFrameCta.addEventListener("click", enterInteractiveDemo);

  // "How It Works" and "Tech" are landing-page sections, not a separate
  // view -- from inside the dashboard a plain anchor jump would land on a
  // display:none element and do nothing, so these route through
  // goToLandingSection() instead (switches back to the landing view first
  // when needed, then scrolls). href="#how-it-works"/"#tech" stay in the
  // markup as a no-JS fallback.
  const navHowItWorksLink = document.getElementById("nav-how-it-works-link");
  if (navHowItWorksLink) {
    navHowItWorksLink.addEventListener("click", (e) => {
      e.preventDefault();
      goToLandingSection("how-it-works");
    });
  }

  const navTechLink = document.getElementById("nav-tech-link");
  if (navTechLink) {
    navTechLink.addEventListener("click", (e) => {
      e.preventDefault();
      goToLandingSection("tech");
    });
  }
}

function initUpload() {
  const dropzone = document.getElementById("dropzone");
  const input = document.getElementById("file-input");
  const errorBox = document.getElementById("upload-error");

  const openPicker = () => input.click();
  dropzone.addEventListener("click", openPicker);
  dropzone.querySelector(".btn").addEventListener("click", (e) => { e.stopPropagation(); openPicker(); });

  ["dragenter", "dragover"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach((evt) =>
    dropzone.addEventListener(evt, (e) => { e.preventDefault(); dropzone.classList.remove("dragover"); }));
  dropzone.addEventListener("drop", (e) => {
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  });
  input.addEventListener("change", () => { if (input.files[0]) handleFile(input.files[0]); });

  document.getElementById("new-session-btn").addEventListener("click", () => {
    errorBox.style.display = "none";
    switchView("landing");
    // The hosted demo can't actually analyze a different video -- send the
    // visitor to the same "run it locally" explanation the landing page
    // itself shows in demo mode, instead of a dropzone that (correctly)
    // isn't there. Local mode is unaffected; this button's label is also
    // swapped to "Run ArcVision locally" in demo mode, see initDemoMode().
    if (window.ARCVISION_MODE === "demo") {
      showDemoUploadNotice();
    }
  });

  async function handleFile(file) {
    errorBox.style.display = "none";

    if (window.ARCVISION_MODE === "demo") {
      showDemoUploadNotice();
      return;
    }

    if (activeJob && (activeJob.status === "processing" || activeJob.status === "queued")) {
      errorBox.textContent = "A session is already being analyzed. Wait for it to finish, or use the " +
        "indicator at the top of the page to check its progress.";
      errorBox.style.display = "block";
      return;
    }

    const check = await validateFileClientSide(file);
    if (!check.ok) {
      errorBox.textContent = check.message;
      errorBox.style.display = "block";
      return;
    }

    try {
      const { session_id } = await Api.upload(file);
      currentSessionId = session_id;
      activeJob = { sessionId: session_id, createdAtMs: Date.now(), status: "processing", error: null };
      persistActiveSession(session_id);
      updateActiveJobIndicator();
      startElapsedTicker();
      switchView("processing");
      setProcessingExpectations(check.durationSec);
      beginPolling(session_id);
    } catch (err) {
      errorBox.textContent = err.message || "Upload failed.";
      errorBox.style.display = "block";
    }
  }
}

function renderStageList(activeStage) {
  const list = document.getElementById("stage-list");
  const activeIdx = STAGE_ORDER.indexOf(activeStage);
  list.innerHTML = STAGE_ORDER.map((stage, i) => {
    const cls = i < activeIdx ? "done" : (i === activeIdx ? "current" : "");
    return `<div class="stage-item ${cls}"><span class="stage-dot"></span>${STAGE_LABELS[stage]}</div>`;
  }).join("");
}

function showLandingError(message) {
  switchView("landing");
  const errorBox = document.getElementById("upload-error");
  errorBox.textContent = message;
  errorBox.style.display = "block";
}

/* True only while the processing screen is the one actually on-screen --
   used everywhere below to decide whether it's OK to pull the user into a
   view change (dashboard on completion, landing on failure) or whether to
   just update the quiet topbar indicator instead, since the job keeps
   running server-side regardless of which view the tab happens to show. */
function isOnProcessingView() {
  const v = document.getElementById("view-processing");
  return !!v && v.classList.contains("active");
}

function beginPolling(sessionId) {
  if (pollTimer) clearInterval(pollTimer);
  // Callers that already know the real current stage (resumeActiveSessionIfAny)
  // render it themselves before calling this; a fresh upload has no stage
  // yet, so it starts the list at the first entry until the first poll tick
  // (within 1.2s) fills in the real one.
  if (isOnProcessingView() && !document.getElementById("stage-list").children.length) {
    renderStageList("validating_video");
  }
  // Tolerate a brief network blip without abandoning a still-running
  // analysis -- only give up (and tell the user) after several consecutive
  // failed status checks, not the first one. Unchanged from the original
  // Day 1 tolerance.
  let consecutiveFailures = 0;
  const MAX_CONSECUTIVE_FAILURES = 5;

  pollTimer = setInterval(async () => {
    let status;
    try {
      status = await Api.status(sessionId);
    } catch (err) {
      consecutiveFailures += 1;
      if (consecutiveFailures >= MAX_CONSECUTIVE_FAILURES) {
        clearInterval(pollTimer);
        const message = "Analysis interrupted — ArcVision lost contact with the local analysis service. " +
          "Your video may need to be analyzed again.";
        clearPersistedActiveSession();
        if (isOnProcessingView()) {
          showLandingError(message);
          activeJob = null;
        } else if (activeJob && activeJob.sessionId === sessionId) {
          activeJob.status = "failed";
          activeJob.error = message;
        }
        updateActiveJobIndicator();
      }
      return;
    }
    consecutiveFailures = 0;

    if (activeJob && activeJob.sessionId === sessionId) {
      activeJob.status = status.status;
      const parsed = Date.parse(status.created_at);
      if (!Number.isNaN(parsed)) activeJob.createdAtMs = parsed;
      updateActiveJobIndicator();
    }

    // Only touch the processing screen's own DOM (progress bar, stage
    // list) while it's actually the visible view -- updating it in the
    // background wastes nothing but there's no reason to, and this keeps
    // the "did I lose my analysis by navigating away" question moot: the
    // poll loop itself never stops just because the user looked at
    // something else.
    if (isOnProcessingView()) {
      document.getElementById("progress-fill").style.width = `${Math.round(status.progress * 100)}%`;
      renderStageList(status.stage);
    }

    if (status.status === "completed") {
      clearInterval(pollTimer);
      clearPersistedActiveSession();
      if (isOnProcessingView()) {
        try {
          const results = await Api.results(sessionId);
          currentResults = results;
          renderDashboard(results);
          switchView("dashboard");
          activeJob = null;
          updateActiveJobIndicator();
        } catch (err) {
          showLandingError(err.message || "Analysis completed, but the results could not be loaded. Check History to try again.");
        }
      }
      // else: leave activeJob at status "completed" -- the topbar
      // indicator now offers a one-click way to open it (see
      // openActiveJobResults), and the session is fully durable in
      // History regardless.
    } else if (status.status === "failed" || status.status === "interrupted") {
      clearInterval(pollTimer);
      clearPersistedActiveSession();
      const message = status.error || "Analysis failed.";
      if (isOnProcessingView()) {
        showLandingError(message);
        activeJob = null;
        updateActiveJobIndicator();
      } else if (activeJob) {
        activeJob.error = message;
      }
    }
  }, 1200);
}

/* ---------------- Dashboard ---------------- */

function initTabs() {
  const tabButtons = document.querySelectorAll(".tab-btn[data-tab]");
  // Only deactivate the panels this tab bar actually owns (tab-coach/shots/
  // replay/details) -- a bare ".tab-panel" query also matches the unrelated
  // standalone #tab-methodology-standalone panel elsewhere in the document,
  // which shares the class only for its show/hide styling. Deactivating that
  // one here left it permanently display:none (its "active" class is only
  // ever set once, in the static HTML) after the first dashboard tab click,
  // breaking the Methodology page for the rest of the session.
  const ownedPanels = Array.from(tabButtons).map((b) => document.getElementById(`tab-${b.dataset.tab}`));
  tabButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      tabButtons.forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      ownedPanels.forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
      if (btn.dataset.tab === "replay") nudgeReplayVideoIfStuck();
    });
  });
}

/* renderReplay() sets the <video>'s src once, up front, while Coach (not
   Replay) is the active tab -- i.e. while the video's ancestor .tab-panel
   is display:none. Some browsers defer or never properly start the actual
   network fetch for a media resource assigned while hidden, leaving the
   element stuck at readyState 0 (HAVE_NOTHING) indefinitely -- a black
   player at 0:00 that never recovers, since nothing ever prompted it to
   try again. Calling .load() here (only if it's still stuck -- a no-op
   safety check, never interrupts a video that's already loading/loaded
   fine) re-issues the resource fetch now that the element is actually
   visible, exactly like the very first render would have if the tab had
   been visible from the start. */
function nudgeReplayVideoIfStuck() {
  const video = document.getElementById("replay-video");
  if (video && video.readyState === 0 && video.src) video.load();
}

function initSubTabs() {
  document.querySelectorAll(".subtab-btn[data-subtab]").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".subtab-btn[data-subtab]").forEach((b) => {
        b.classList.remove("active");
        b.setAttribute("aria-selected", "false");
      });
      document.querySelectorAll(".subtab-panel").forEach((p) => p.classList.remove("active"));
      btn.classList.add("active");
      btn.setAttribute("aria-selected", "true");
      document.getElementById(`subtab-${btn.dataset.subtab}`).classList.add("active");
    });
  });
}

function fmt(v, digits = 2, suffix = "") {
  if (v === null || v === undefined) return "&mdash;";
  return `${Number(v).toFixed(digits)}${suffix}`;
}

function warningBanner(text) {
  return `<div class="warning-banner">${text}</div>`;
}

function humanize(s) {
  return s ? s.replace(/_/g, " ") : "&mdash;";
}

/* Presentation-only bucketing for a raw 0-1 confidence/quality value, so it
   can be scanned at a glance via the existing high/medium/low badge style
   (already used for findings and session-history status). This never feeds
   back into any detection/tracking/classification decision -- it's purely
   how the same already-computed number is displayed. */
function confidenceTier(v) {
  if (v === null || v === undefined) return null;
  if (v >= 0.7) return "high";
  if (v >= 0.4) return "medium";
  return "low";
}

function confidenceCell(v) {
  const tier = confidenceTier(v);
  if (tier === null) return "&mdash;";
  return `${fmt(v)} <span class="confidence-badge ${tier}">${tier}</span>`;
}

/* ---------------- Coach (presentation-only translation of app.analytics.coaching's
   already-computed, already-selected output -- this file never re-derives
   which finding is shown, only how it's worded/laid out). ---------------- */

const CONFIDENCE_LANGUAGE = { high: "Strong evidence", medium: "Moderate evidence", low: "Limited evidence" };

// Keyed by coaching.py's own exact reason strings (small, closed set it
// controls) so the empty state can be warm and specific; anything
// unrecognized still renders honestly via the generic fallback below
// rather than looking broken.
const MVM_EMPTY_STATES = {
  "No strong measurable difference was found between your makes and misses this session.": {
    title: "No clear make-vs-miss difference this session",
    body: "Your measured mechanics didn't show a strong enough difference for ArcVision to confidently attribute one to makes vs. misses.",
  },
  "Not enough shots were detected this session to compare makes vs. misses reliably.": {
    title: "Not enough shots yet to compare",
    body: "Take a few more shots so ArcVision has enough makes and misses to compare.",
  },
  "Not enough confidently-made and confidently-missed shots were detected this session to compare them reliably.": {
    title: "Not enough makes and misses yet to compare",
    body: "ArcVision needs a handful of confidently-classified makes and misses to compare -- take a few more shots.",
  },
};

function renderCues(cues) {
  if (!cues || !cues.length) return "";
  const [primary, ...rest] = cues;
  return `
    <div class="coach-cues">
      <div class="coach-cues-label">Try this next</div>
      <div class="coach-cue-primary">${primary.text}</div>
      ${rest.map((c) => `<div class="coach-cue-secondary">${c.text}</div>`).join("")}
    </div>`;
}

function renderEvidenceDisclosure(finding, sourceLabel, confidence) {
  const detail = finding.evidence.detail || {};
  const detailRows = Object.entries(detail)
    .map(([k, v]) => `<tr><td>${humanize(k)}</td><td class="num">${v === null || v === undefined ? "&mdash;" : v}</td></tr>`)
    .join("");
  return `
    <details class="coach-evidence">
      <summary>Why ArcVision thinks this</summary>
      <p>${finding.evidence.text}</p>
      <table class="metric-table"><tbody>
        <tr><td>Measured metric</td><td class="num">${finding.metric_label}</td></tr>
        ${sourceLabel ? `<tr><td>Evidence source</td><td class="num">${sourceLabel}</td></tr>` : ""}
        ${confidence ? `<tr><td>Confidence</td><td class="num">${CONFIDENCE_LANGUAGE[confidence] || confidence}</td></tr>` : ""}
        ${detailRows}
      </tbody></table>
    </details>`;
}

function renderFocusHero(coaching) {
  if (!coaching.priority) {
    return `
      <div class="coach-focus coach-focus-empty">
        <div class="coach-focus-eyebrow">Your #1 focus</div>
        <p>Not enough evidence yet this session to point to one clear priority — take a few more shots and check back.</p>
      </div>`;
  }
  const p = coaching.priority;
  const sourceLabel = p.source === "makes_vs_misses" ? "Makes vs. misses comparison" : "Shot-to-shot consistency";
  return `
    <div class="coach-focus">
      <div class="coach-focus-eyebrow">Your #1 focus</div>
      <h2>${p.concept || p.metric_label}</h2>
      <p class="coach-focus-evidence">${p.noticed_text}</p>
      ${p.meaning_text ? `
      <div class="coach-focus-meaning">
        <div class="coach-focus-meaning-label">What this means</div>
        <p>${p.meaning_text}</p>
      </div>` : ""}
      ${renderCues(p.cues)}
      ${renderEvidenceDisclosure(p, sourceLabel, p.confidence)}
    </div>`;
}

function renderStrengthCard(coaching) {
  if (!coaching.strength) {
    return `<div class="card coach-card-empty"><div class="coach-card-eyebrow">Keep this</div><p>Not enough shot-to-shot data yet to call out a strongest mechanic.</p></div>`;
  }
  const s = coaching.strength;
  // Basketball meaning first (noticed_text, e.g. "Your lower-body position
  // at release was one of the most repeatable parts of your shot."), then
  // the specific measurement as supporting detail -- see coaching.py's
  // _STRENGTH_INTRO for why these are deliberately two separate sentences.
  return `
    <div class="card coach-card-strength">
      <div class="coach-card-eyebrow">Keep this</div>
      <h3>${s.concept || s.metric_label}</h3>
      <p>${s.noticed_text}</p>
      <p class="coach-card-strength-detail">Your ${s.metric_label.toLowerCase()} stayed relatively consistent across the session.</p>
      ${renderEvidenceDisclosure(s, "Shot-to-shot consistency", null)}
    </div>`;
}

function renderMvmSection(coaching) {
  if (coaching.makes_vs_misses_note) {
    return `
      <div class="card coach-card-mvm">
        <div class="coach-card-eyebrow">Makes vs. misses</div>
        <p>${coaching.makes_vs_misses_note.text}</p>
      </div>`;
  }
  const known = MVM_EMPTY_STATES[coaching.makes_vs_misses_reason];
  const title = known ? known.title : "Not enough makes/misses yet to compare";
  const body = known ? known.body : (coaching.makes_vs_misses_reason || "Take a few more shots so ArcVision can compare your makes and misses.");
  return `
    <div class="card coach-card-mvm coach-card-empty">
      <div class="coach-card-eyebrow">Makes vs. misses</div>
      <h3>${title}</h3>
      <p>${body}</p>
    </div>`;
}

function renderCoachAbstain(coaching) {
  return `
    <div class="coach-abstain">
      <div class="coach-abstain-icon" aria-hidden="true">
        <svg viewBox="0 0 24 24" width="34" height="34" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="9"/>
          <path d="M9.4 9.4a2.6 2.6 0 1 1 3.6 3.4c-.9.6-1 1-1 1.7"/>
          <path d="M12 16.6h.01"/>
        </svg>
      </div>
      <h2>ArcVision needs a bit more to work with</h2>
      <p>${coaching.coach_note}</p>
    </div>`;
}

function renderCoachHeader(data) {
  const s = data.session_summary;
  const coaching = data.coaching;
  const classified = s.made + s.missed;
  const shootingText = s.shooting_percentage !== null ? `${s.shooting_percentage}%` : "&mdash;";
  const confLabel = (coaching && coaching.eligible) ? (CONFIDENCE_LANGUAGE[coaching.confidence] || null) : null;
  return `
    <div class="coach-stats">
      <div class="coach-stat"><span class="coach-stat-value">${s.total_shots_detected}</span><span class="coach-stat-label">Shots</span></div>
      <div class="coach-stat"><span class="coach-stat-value">${s.made}</span><span class="coach-stat-label">Made</span></div>
      <div class="coach-stat"><span class="coach-stat-value">${s.missed}</span><span class="coach-stat-label">Missed</span></div>
      <div class="coach-stat"><span class="coach-stat-value">${shootingText}</span><span class="coach-stat-label">Shooting %${classified ? ` &middot; ${classified} classified` : ""}</span></div>
      ${s.unknown ? `<div class="coach-stat"><span class="coach-stat-value">${s.unknown}</span><span class="coach-stat-label">Unclassified</span></div>` : ""}
      ${confLabel ? `<div class="coach-confidence-pill">${confLabel}</div>` : ""}
    </div>`;
}

function renderCoach(data) {
  const container = document.getElementById("tab-coach");
  const coaching = data.coaching;

  if (!coaching) {
    // Session predates the Coach feature -- explain plainly instead of a
    // blank/broken-looking panel.
    container.innerHTML = `
      ${renderCoachHeader(data)}
      <div class="coach-abstain">
        <h2>Coach feedback isn't available for this session</h2>
        <p>This session was analyzed before ArcVision Coach existed. Analyze a new video, or check Details for the full underlying metrics.</p>
      </div>`;
    return;
  }

  if (!coaching.eligible) {
    container.innerHTML = `${renderCoachHeader(data)}${renderCoachAbstain(coaching)}`;
    return;
  }

  const qualityCaveat = (coaching.data_quality_notes && coaching.data_quality_notes.length)
    ? warningBanner(coaching.data_quality_notes.join(" ")) : "";

  container.innerHTML = `
    ${renderCoachHeader(data)}
    ${qualityCaveat}
    <div class="coach-note-block"><p>${coaching.coach_note}</p></div>
    ${renderFocusHero(coaching)}
    <div class="coach-secondary-grid">
      ${renderStrengthCard(coaching)}
      ${renderMvmSection(coaching)}
    </div>
  `;
}

/* ---------------- Details (Mechanics / Makes vs Misses / Consistency / Trends) ---------------- */

function renderDetails(data) {
  renderMechanics(data);
  renderMvm(data);
  renderConsistency(data);
  renderTrends(data);
}

function renderDashboard(data) {
  renderDemoBanner();
  document.getElementById("dash-filename").textContent = data.original_filename || "Session";
  const meta = data.video_meta;
  document.getElementById("dash-sub").textContent =
    `${meta.duration_sec.toFixed(1)}s &middot; ${meta.width}x${meta.height} &middot; analyzed at ${data.analysis_fps.toFixed(1)} fps`.replace(/&middot;/g, "·");

  const warnBox = document.getElementById("dash-warnings");
  warnBox.innerHTML = (data.warnings || []).map(warningBanner).join("");

  renderCoach(data);
  renderShots(data);
  renderReplay(data);
  renderDetails(data);
}

function outcomeClass(o) { return `outcome-${o}`; }

/* A shot carries a `verified_outcome` ONLY in the one precomputed final-demo
   session (added by scripts/export_demo.py -- never set anywhere else, never
   by any production/local analysis). Every other display path falls back to
   the real automatic prediction exactly as before. See docs/FINAL_DEMO_GROUND_TRUTH.md. */
function displayOutcome(s) { return s.verified_outcome || s.outcome; }

function renderShots(data) {
  const shots = data.shots || [];
  if (!shots.length) {
    document.getElementById("tab-shots").innerHTML = `<div class="empty-state">No shots were detected in this video.</div>`;
    return;
  }
  const chips = shots.map((s) => `
    <div class="shot-chip" data-shot="${s.shot_index}">
      <span class="n">#${s.shot_index}</span>
      <span class="outcome-dot ${outcomeClass(displayOutcome(s))}"></span>
    </div>`).join("");

  document.getElementById("tab-shots").innerHTML = `
    <div class="shot-list">${chips}</div>
    <div class="card" id="shot-detail"></div>
  `;

  function selectShot(idx) {
    document.querySelectorAll(".shot-chip").forEach((c) => c.classList.toggle("active", Number(c.dataset.shot) === idx));
    renderShotDetail(shots.find((s) => s.shot_index === idx));
  }
  document.querySelectorAll(".shot-chip").forEach((chip) => {
    chip.addEventListener("click", () => selectShot(Number(chip.dataset.shot)));
  });
  selectShot(shots[0].shot_index);
}

/* Presentation-only translation of the real, unmodified warning vocabulary
   produced by app/events/shot_state_machine.py, app/biomechanics/metrics.py,
   and app/analytics/shot_record.py (every code below was found by reading
   those three files' actual warnings.append(...) call sites, not guessed).
   Never changes which warnings are generated or when -- only how an already
   -generated code is worded for a player instead of a developer. Unknown
   codes still render (via humanize()), just without custom copy, so a
   future warning is never silently dropped. */
const WARNING_INFO = {
  video_ended_during_flight: {
    title: "Clip ended mid-shot",
    body: "The video ended before ArcVision could confirm this shot's flight was complete, so some late-flight measurements may be missing.",
  },
  short_duration: {
    title: "Shorter flight than expected",
    body: "This shot's tracked flight was brief, which can happen with a quick release or a partial tracking gap — some measurements may be less precise.",
  },
  max_duration_exceeded: {
    title: "Shot tracking incomplete",
    body: "ArcVision couldn't confidently track the full shot sequence, so some measurements may be less reliable.",
  },
  closed_after_prolonged_ball_tracking_dropout: {
    title: "Ball tracking interrupted",
    body: "ArcVision lost track of the ball for an extended stretch during this shot, so some measurements may be less reliable.",
  },
  load_phase_inferred_from_pose_only_ball_not_tracked_near_hand: {
    title: "Load phase estimated from pose",
    body: "ArcVision didn't directly track the ball near your hand before this shot, so the set-up timing was estimated from your body position instead.",
  },
  shot_window_incomplete: {
    title: "Shot boundaries unclear",
    body: "ArcVision couldn't clearly determine where this shot's motion started and ended, so mechanics for this shot are limited.",
  },
  no_detected_pose_frames_in_window: {
    title: "Pose not tracked",
    body: "ArcVision couldn't detect your pose during this shot's window, so mechanics measurements aren't available.",
  },
  knee_angle_unavailable_at_load: {
    title: "Knee angle unavailable at load",
    body: "ArcVision couldn't get a clear view of your knees at the set point, so knee-bend measurements aren't available for this shot.",
  },
  pose_unavailable_at_release: {
    title: "Pose not visible at release",
    body: "ArcVision couldn't detect your pose at the moment of release, so release-form measurements aren't available.",
  },
  shooting_arm_landmarks_low_confidence_at_release: {
    title: "Limited pose confidence at release",
    body: "ArcVision had difficulty seeing your shooting arm clearly at release, so release-form measurements may be less reliable.",
  },
  no_ball_trajectory_during_flight: {
    title: "Ball not tracked during flight",
    body: "ArcVision didn't track the ball during this shot's flight, so trajectory measurements (arc height, flight path) aren't available.",
  },
  insufficient_reliable_points_for_straightness: {
    title: "Limited flight tracking",
    body: "ArcVision only tracked a few reliable points during this shot's flight, so the flight-path measurement isn't available.",
  },
  apex_height_unavailable: {
    title: "Arc height unavailable",
    body: "ArcVision couldn't measure how high this shot arced, usually because part of the flight wasn't reliably tracked.",
  },
  release_could_not_be_estimated: {
    title: "Release not detected",
    body: "ArcVision couldn't pinpoint this shot's release, so it's excluded from session-level analysis (it's still shown here for reference).",
  },
  low_pose_confidence_for_this_shot: {
    title: "Lower overall tracking confidence",
    body: "Pose tracking was less reliable than usual for this shot, so treat its measurements as a rough read.",
  },
};
const EXCLUSION_REASON_INFO = {
  no_release_detected: {
    title: "Excluded from session analysis",
    body: "This shot's release couldn't be confidently detected, so it isn't included in session-level comparisons — but its raw data is still shown below.",
  },
};

function friendlyWarning(code) {
  return WARNING_INFO[code] || { title: humanize(code), body: null };
}

const TRACKING_QUALITY_LABELS = { high: "high", medium: "medium", low: "low", excluded: "no reliable data" };
function trackingQualityBadge(level) {
  if (!level) return "&mdash;";
  const cls = level === "excluded" ? "critical" : level;
  return `<span class="confidence-badge ${cls}">${TRACKING_QUALITY_LABELS[level] || level}</span>`;
}

function _qualityPanelBody(items, rawCodes) {
  return `
      <ul class="quality-panel-list">
        ${items.map((it) => `<li><strong>${it.title}</strong>${it.body ? `<span>${it.body}</span>` : ""}</li>`).join("")}
      </ul>
      <details class="coach-evidence quality-panel-tech">
        <summary>Technical details</summary>
        <p>${rawCodes.map(humanize).join(" &middot; ")}</p>
      </details>`;
}

/* One compact panel combining every quality note for a shot, instead of a
   repeated warning-banner per code -- these are informational (tracking/
   measurement caveats), not errors, so they get a distinct, calmer style
   from the session-level .warning-banner (still used, unchanged,
   elsewhere for genuine session issues like an unlocated hoop).

   `collapseIfOrdinary` (verified demo mode only -- normal/local sessions
   always pass false, unchanged from before this existed): ordinary
   measurement-quality notes default to collapsed so the shot-detail view
   reads as a basketball analysis page first, not a diagnostic report --
   but a genuinely fatal/excluded condition (shot.excluded_from_analysis,
   ArcVision's own existing distinction from an ordinary caveat) always
   stays fully expanded and prominent, in every mode, because that shot's
   analysis really was meaningfully impaired. Nothing here removes,
   rewrites, or falsifies a single warning code or its data -- only
   whether the ordinary-case panel starts open or closed. */
function renderQualityPanel(shot, mechWarnings, trajWarnings, collapseIfOrdinary) {
  const codes = [...(shot.warnings || []), ...mechWarnings, ...trajWarnings];
  const exclusionInfo = shot.excluded_from_analysis
    ? (EXCLUSION_REASON_INFO[shot.exclusion_reason] || { title: "Excluded from session analysis", body: humanize(shot.exclusion_reason) })
    : null;
  if (!codes.length && !exclusionInfo) return "";

  const items = exclusionInfo ? [exclusionInfo, ...codes.map(friendlyWarning)] : codes.map(friendlyWarning);
  const rawCodes = [...(exclusionInfo ? [`exclusion_reason: ${shot.exclusion_reason}`] : []), ...codes];

  if (collapseIfOrdinary && !exclusionInfo) {
    return `
    <details class="coach-evidence quality-panel-collapsed">
      <summary>Measurement notes (${items.length})</summary>
      <div class="quality-panel">
        ${_qualityPanelBody(items, rawCodes)}
      </div>
    </details>`;
  }

  return `
    <div class="quality-panel">
      <div class="quality-panel-header">
        <span class="quality-panel-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="9"/><path d="M12 8v5"/><path d="M12 16h.01"/>
          </svg>
        </span>
        <span>${items.length > 1 ? `${items.length} quality notes for this shot` : "Quality note for this shot"}</span>
      </div>
      ${_qualityPanelBody(items, rawCodes)}
    </div>`;
}

function renderShotDetail(shot) {
  const m = shot.mechanics, t = shot.trajectory;
  const verified = shot.verified_outcome;
  // Verified demo shots: the primary Outcome row is simply the verified
  // result with a small, restrained "VERIFIED" label -- not the automatic
  // classifier's call, so it never belongs in the same row as a
  // confidence score. The automatic prediction/confidence/reason/evidence
  // are not rendered anywhere in this featured session's shot detail (see
  // the verified-branch template below) -- presentation-only, the data
  // itself (automatic_outcome, outcome_confidence, outcome_reason,
  // outcome_evidence) remains fully preserved in the exported session.json.
  const outcomeRows = verified
    ? [["Outcome", `${verified.toUpperCase()} <span class="verified-badge">VERIFIED</span>`]]
    : [
        ["Outcome", `${shot.outcome.toUpperCase()} &mdash; ${confidenceCell(shot.outcome_confidence)}`],
        ["Reason", humanize(shot.outcome_reason)],
      ];
  // Shooting side is hidden for the featured public demo only: the wrist-
  // to-ball-distance heuristic it comes from can't reliably tell the
  // shooting arm apart from the guide arm on this session's side/profile
  // camera angle (investigated directly against this session's real pose
  // data -- see app/biomechanics/shooting_side.py's docstring), so this
  // session would confidently show a wrong value for it on every shot. A
  // missing minor field beats a confidently wrong one. `verified` (shot.
  // verified_outcome) is the same existing signal already used two lines
  // up to distinguish this one frozen, manually-verified session from a
  // normal local upload -- no new session-ID check. Every other field,
  // and shooting_side itself in the underlying data, is untouched; a
  // local upload (verified always undefined there) still shows this row
  // exactly as before.
  const rows = [
    ...outcomeRows,
    ["Tracking quality for this shot", trackingQualityBadge(shot.overall_confidence_level)],
    ...(verified ? [] : [["Shooting side", shot.shooting_side || "undetermined"]]),
    ["Release time", shot.release_time_sec !== null ? `${shot.release_time_sec.toFixed(2)}s` : "unavailable"],
    ["Release confidence", confidenceCell(shot.release_confidence)],
    ["Pose quality", confidenceCell(shot.pose_quality)],
    ["Ball track quality", confidenceCell(shot.ball_track_quality)],
    ["Hoop confidence", confidenceCell(shot.hoop_confidence)],
    ["Knee angle (load / release)", `${fmt(m.knee_angle_at_load_deg, 1, "&deg;")} / ${fmt(m.knee_angle_at_release_deg, 1, "&deg;")}`],
    ["Elbow angle (load / release)", `${fmt(m.elbow_angle_at_load_deg, 1, "&deg;")} / ${fmt(m.elbow_angle_at_release_deg, 1, "&deg;")}`],
    ["Torso lean (load / release)", `${fmt(m.torso_lean_at_load_deg, 1, "&deg;")} / ${fmt(m.torso_lean_at_release_deg, 1, "&deg;")}`],
    ["Release height (rel. to hip)", fmt(m.release_height_norm, 2, " body-lengths")],
    ["Load / upward / total prep duration", `${fmt(m.load_duration_sec, 2, "s")} / ${fmt(m.upward_duration_sec, 2, "s")} / ${fmt(m.total_prep_duration_sec, 2, "s")}`],
    ["Trajectory straightness", fmt(t.straightness_ratio, 2)],
    ["Trajectory apex height", fmt(t.apex_height_norm, 2, " body-lengths")],
  ];
  // Verified demo mode: ordinary measurement notes collapse by default (a
  // genuinely fatal/excluded shot still renders fully expanded regardless
  // -- see renderQualityPanel) and the panel moves below the mechanics
  // table, so the page reads as a basketball analysis first and a
  // diagnostic report second. Normal/local sessions are completely
  // unchanged: same collapseIfOrdinary=false behavior and same
  // before-the-table position as before this pass.
  const qualityPanel = renderQualityPanel(shot, m.warnings || [], t.warnings || [], !!verified);
  const evidence = shot.outcome_evidence || {};
  const evidenceRows = Object.entries(evidence).filter(([k]) => k !== "why");
  const evidenceSection = evidenceRows.length ? `
      <h3 style="margin-top:18px;">Outcome evidence</h3>
      <div class="card-sub">${evidence.why || ""}</div>
      <table class="metric-table"><tbody>
        ${evidenceRows.map(([k, v]) => `<tr><td>${k.replace(/_/g, " ")}</td><td class="num">${v}</td></tr>`).join("")}
      </tbody></table>
  ` : "";
  const explainerText = verified
    ? "Quality notes highlight parts of the shot where tracking or pose visibility may affect the reliability of individual measurements."
    : "Outcome confidence reflects how clearly ArcVision saw this shot's result. Tracking quality reflects how "
      + "reliably your pose and the ball were tracked during the shot itself — the two are independent, so a "
      + "confident outcome can still come with lower-confidence measurements below.";
  const metricTable = `
    <table class="metric-table"><tbody>
      ${rows.map(([k, v]) => `<tr><td>${k}</td><td class="num">${v}</td></tr>`).join("")}
    </tbody></table>`;
  // Verified demo shots: the automatic classifier's own prediction/reason/
  // evidence is real, useful engineering information, but showing it --
  // even collapsed -- next to a manually-verified result reads as
  // confusing in a public portfolio demo (a VERIFIED MADE shot with an
  // expandable "MISSED" underneath it). Presentation-only: automatic_
  // outcome/outcome_confidence/outcome_reason/outcome_evidence are all
  // still exported untouched in session.json (see scripts/export_demo.py's
  // apply_verified_outcomes -- never overwritten, never deleted), this
  // just stops rendering them in this one UI location for this one
  // session. `verified` (shot.verified_outcome) is the same existing
  // signal already used above (Outcome row, Shooting side row) to
  // distinguish this one frozen, manually-verified session from a normal
  // local upload -- no new session-ID check. A local upload (verified
  // always undefined) keeps showing its automatic evidence exactly as
  // before, via `evidenceSection` in the branch below.
  document.getElementById("shot-detail").innerHTML = verified
    ? `
    <h3>Shot ${shot.shot_index}</h3>
    <div class="card-sub">${explainerText}</div>
    ${metricTable}
    ${qualityPanel}
  `
    : `
    <h3>Shot ${shot.shot_index}</h3>
    <div class="card-sub">${explainerText}</div>
    ${qualityPanel}
    ${metricTable}
    ${evidenceSection}
  `;
}

const MECHANICS_METRICS = [
  { key: "knee_angle_at_release_deg", label: "Knee angle at release", unit: "°", path: (s) => s.mechanics.knee_angle_at_release_deg },
  { key: "elbow_angle_at_release_deg", label: "Elbow angle at release", unit: "°", path: (s) => s.mechanics.elbow_angle_at_release_deg },
  { key: "torso_lean_at_release_deg", label: "Torso lean at release", unit: "°", path: (s) => s.mechanics.torso_lean_at_release_deg },
  { key: "release_height_norm", label: "Release height (body-lengths above hip)", unit: "", path: (s) => s.mechanics.release_height_norm },
  { key: "total_prep_duration_sec", label: "Total prep-to-release duration", unit: "s", path: (s) => s.mechanics.total_prep_duration_sec },
];

/* Mirrors app/analytics/metric_extractors.py's registry so the frontend can
   pull the REAL per-shot values behind a makes-vs-misses comparison (the
   backend's ComparisonResult only carries summary stats, not raw values --
   plotting real per-shot points here instead of fabricating them from a
   mean keeps the chart honest). Matched by label since that's what the
   backend's ComparisonResult.metric_name already contains. */
const ALL_METRICS_BY_LABEL = {
  "Knee angle at load (deepest bend)": (s) => s.mechanics.knee_angle_at_load_deg,
  "Knee angle at release": (s) => s.mechanics.knee_angle_at_release_deg,
  "Elbow angle at load": (s) => s.mechanics.elbow_angle_at_load_deg,
  "Elbow angle at release": (s) => s.mechanics.elbow_angle_at_release_deg,
  "Torso lean at load": (s) => s.mechanics.torso_lean_at_load_deg,
  "Torso lean at release": (s) => s.mechanics.torso_lean_at_release_deg,
  "Release height (relative to hip, body-lengths)": (s) => s.mechanics.release_height_norm,
  "Release horizontal offset from shoulder": (s) => s.mechanics.release_horizontal_offset_norm,
  "Load phase duration": (s) => s.mechanics.load_duration_sec,
  "Upward-motion duration": (s) => s.mechanics.upward_duration_sec,
  "Total prep-to-release duration": (s) => s.mechanics.total_prep_duration_sec,
  "Trajectory apex height (body-lengths above release)": (s) => s.trajectory.apex_height_norm,
  "Trajectory straightness (1.0 = perfectly straight)": (s) => s.trajectory.straightness_ratio,
};

function renderMechanics(data) {
  const shots = data.shots || [];
  const container = document.getElementById("subtab-mechanics");
  if (!shots.length) { container.innerHTML = `<div class="empty-state">No shots to analyze.</div>`; return; }

  // Per-shot outcome coloring/grouping must follow the same primary-outcome
  // semantics as the rest of the app (displayOutcome: verified_outcome when
  // present, else the automatic outcome) -- computed once here since it's
  // the same per shot across every metric's chart below.
  const outcomes = shots.map((s) => displayOutcome(s));
  const legendRow = outcomeLegendRow(outcomes);
  const chartSubCopy = shots.some((s) => s.verified_outcome)
    ? "Per shot, colored by verified outcome."
    : "Per shot, colored by outcome.";

  // Computed once per metric, up front, so the same values feed both the
  // "is a shot missing here" note below and the actual chart draw -- never
  // recomputed or altered between the two.
  const metricValues = MECHANICS_METRICS.map((m) => shots.map((s) => m.path(s)));

  container.innerHTML = `
    <div class="card details-explainer">
      <p>Measurements ArcVision derived from the video for each shot. If a shot has no value on a chart, that mechanic wasn't reliably measurable for that shot.</p>
    </div>
    <div class="metric-chart-grid">${MECHANICS_METRICS.map((m, i) => `
    <div class="card">
      <h3>${m.label}</h3>
      <div class="card-sub">${chartSubCopy}</div>
      ${legendRow}
      <div id="chart-${m.key}"></div>
      ${omittedShotsNote(metricValues[i])}
    </div>
  `).join("")}</div>`;

  MECHANICS_METRICS.forEach((m, i) => {
    Charts.perShotBarChart(document.getElementById(`chart-${m.key}`), { values: metricValues[i], outcomes, unit: m.unit });
  });
}

/* Chart footnote, shown only when this specific metric's real per-shot
   values actually omit one or more shots (a genuinely missing measurement
   -- never fabricated, interpolated, or replaced; see perShotBarChart,
   which already just skips null/undefined points). Purely informational:
   without this, an absent bar can read as a rendering bug rather than
   "ArcVision didn't have a reliable measurement for this shot." */
function omittedShotsNote(values) {
  const omitted = values.some((v) => v === null || v === undefined);
  if (!omitted) return "";
  return `<div class="chart-note">Some shots are omitted when a reliable measurement wasn't available.</div>`;
}

/* Shared by every outcome-colored chart's legend: only list the outcome
   categories actually present in what's being displayed, in a fixed
   made/missed/unknown order. For the verified demo (every shot resolved to
   made/missed) this means "Unknown" simply never appears -- not hidden by
   a special-case demo flag, just because outcomes here never contains it.
   A normal session with a real automatically-unknown shot still shows it. */
function outcomeLegendRow(outcomes) {
  const present = new Set(outcomes);
  const items = [
    present.has("made") ? ["--good", "Made"] : null,
    present.has("missed") ? ["--critical", "Missed"] : null,
    present.has("unknown") ? ["--unknown", "Unknown"] : null,
  ].filter(Boolean);
  return `<div class="legend-row">${items.map(([color, label]) =>
    `<div class="legend-item"><span class="legend-swatch" style="background:var(${color})"></span>${label}</div>`
  ).join("")}</div>`;
}

/* Plain-English direction sentence for one makes-vs-misses comparison --
   reused by both the ranked chart's tooltip context and the session
   takeaway below. Never invents a threshold or causal claim: it only
   restates which group's real, already-computed mean was higher. */
function mvmDirectionSentence(c) {
  const higher = c.made_mean > c.missed_mean ? "made" : "missed";
  return `Measured higher on your ${higher} shots than your ${higher === "made" ? "missed" : "made"} shots this session (${c.effect_label} effect size).`;
}

function renderMvm(data) {
  const mvm = data.makes_vs_misses;
  const container = document.getElementById("subtab-mvm");
  const shots = data.shots || [];
  if (!mvm.eligible) {
    const reasonText = {
      not_enough_total_shots: "Not enough shots were detected this session to compare makes vs. misses reliably.",
      not_enough_made_or_missed_shots: "Not enough confidently-made or confidently-missed shots were detected yet.",
    }[mvm.reason] || "Insufficient data.";
    container.innerHTML = `<div class="empty-state">${reasonText}<br>Made: ${mvm.made_count} &middot; Missed: ${mvm.missed_count} &middot; Unknown: ${mvm.unknown_count}</div>`;
    return;
  }

  const ranked = mvm.comparisons
    .filter((c) => c.sufficient_sample && c.effect_size !== null)
    .sort((a, b) => Math.abs(b.effect_size) - Math.abs(a.effect_size));

  // The made/missed groups behind this comparison always come from
  // ArcVision's own outcome detection (app/analytics/makes_vs_misses.py
  // runs before any verified outcome exists) -- in the one session with
  // frozen verified outcomes, that grouping can genuinely disagree with
  // the verified badges shown in Coach/Shots/Replay, so this is called
  // out explicitly rather than left to look inconsistent.
  const hasVerified = shots.some((s) => s.verified_outcome);
  const top = ranked[0];

  container.innerHTML = `
    <div class="card details-explainer">
      <div class="coach-card-eyebrow">How to read this</div>
      <p>This ranks the mechanics that differed most between your made and missed shots this session. Bar length is the
        <strong>size</strong> of the difference; direction shows which group measured higher. These are standardized
        effect sizes, not raw degrees or seconds &mdash; they describe this session's data, not proof that a mechanic caused a make or a miss.</p>
      ${hasVerified ? `<p>Made/Missed groups here follow ArcVision's own shot outcome detection for this session, which can differ from the manually verified outcomes shown in Coach, Shots, and Replay.</p>` : ""}
    </div>
    ${top ? `
    <div class="card session-takeaway">
      <div class="session-takeaway-eyebrow">Biggest measured difference</div>
      <h3>${top.metric_name}</h3>
      <p>${mvmDirectionSentence(top)}</p>
    </div>` : ""}
    <div class="card">
      <h3>Ranked differentiators (effect size)</h3>
      <div class="card-sub">Positive = higher on made shots. Made n=${mvm.made_count}, Missed n=${mvm.missed_count}.</div>
      <div id="mvm-ranked"></div>
    </div>
    <div class="card">
      <h3>Metric-by-metric comparison</h3>
      <table class="metric-table">
        <thead><tr><th>Metric</th><th>Made mean</th><th>Missed mean</th><th>Effect size</th><th>n (made/missed)</th></tr></thead>
        <tbody>
          ${mvm.comparisons.map((c) => `
            <tr>
              <td>${c.metric_name}</td>
              <td class="num">${fmt(c.made_mean)}</td>
              <td class="num">${fmt(c.missed_mean)}</td>
              <td class="num">${c.sufficient_sample ? `${fmt(c.effect_size)} (${c.effect_label})` : "&mdash;"}</td>
              <td class="num">${c.made_n}/${c.missed_n}</td>
            </tr>`).join("")}
        </tbody>
      </table>
    </div>
    ${mvm.comparisons.filter((c) => c.sufficient_sample).map((c) => `
      <div class="card">
        <h3>${c.metric_name}</h3>
        <div class="card-sub">Difference: ${fmt(c.difference)} &middot; effect size ${fmt(c.effect_size)} (${c.effect_label})${c.p_value !== null ? ` &middot; p=${c.p_value}` : ""}</div>
        <div id="strip-${c.metric_name.replace(/[^a-z0-9]/gi, "")}"></div>
      </div>`).join("")}
  `;

  Charts.rankedHBar(document.getElementById("mvm-ranked"), {
    items: ranked.map((c) => ({ label: c.metric_name, value: c.effect_size })),
  });

  mvm.comparisons.filter((c) => c.sufficient_sample).forEach((c) => {
    const el = document.getElementById(`strip-${c.metric_name.replace(/[^a-z0-9]/gi, "")}`);
    const getter = ALL_METRICS_BY_LABEL[c.metric_name];
    const madeValues = getter ? shots.filter((s) => s.outcome === "made" && !s.excluded_from_analysis).map(getter).filter((v) => v !== null && v !== undefined) : [];
    const missedValues = getter ? shots.filter((s) => s.outcome === "missed" && !s.excluded_from_analysis).map(getter).filter((v) => v !== null && v !== undefined) : [];
    Charts.madeVsMissedStrip(el, { madeValues, missedValues });
  });
}

function renderConsistency(data) {
  const results = data.consistency || [];
  const container = document.getElementById("subtab-consistency");
  const sufficient = results.filter((r) => r.sufficient_sample && r.coefficient_of_variation !== null);
  if (!sufficient.length) {
    container.innerHTML = `<div class="empty-state">Not enough shots yet for shot-to-shot consistency analysis.</div>`;
    return;
  }
  const sorted = [...sufficient].sort((a, b) => a.coefficient_of_variation - b.coefficient_of_variation);
  container.innerHTML = `
    <div class="card details-explainer">
      <p>How repeatable each measured mechanic was across your shots this session, independent of whether they went in. A lower coefficient of variation means that mechanic stayed more consistent shot to shot.</p>
    </div>
    <div class="card">
      <h3>Shot-to-shot consistency</h3>
      <div class="card-sub">Coefficient of variation (std. dev. &divide; mean) per metric &mdash; lower means more consistent across your shots.</div>
      <div id="consistency-chart"></div>
    </div>
    <div class="card">
      <h3>All metrics</h3>
      <table class="metric-table">
        <thead><tr><th>Metric</th><th>Mean</th><th>Std dev</th><th>CV</th><th>n</th></tr></thead>
        <tbody>
          ${results.map((r) => `
            <tr><td>${r.label}</td><td class="num">${fmt(r.mean_value)}</td><td class="num">${fmt(r.std_dev)}</td>
              <td class="num">${r.sufficient_sample ? fmt(r.coefficient_of_variation, 3) : "&mdash;"}</td><td class="num">${r.n}</td></tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
  Charts.rankedHBar(document.getElementById("consistency-chart"), {
    items: sorted.map((r) => ({ label: r.label, value: r.coefficient_of_variation })),
    valueFmt: (v) => v.toFixed(3),
  });
}

function renderTrends(data) {
  const t = data.trends;
  const container = document.getElementById("subtab-trends");
  if (!t.eligible) {
    container.innerHTML = `<div class="empty-state">Not enough shots yet for early-vs-late session trend analysis.</div>`;
    return;
  }
  const notable = t.metric_trends.filter((m) => m.change !== null && m.early_n >= 2 && m.late_n >= 2);
  container.innerHTML = `
    <div class="card details-explainer">
      <p>Compares the first half of this session's shots to the second half &mdash; for shooting percentage and any mechanic with enough data in both halves. This is a two-point comparison, not a shot-by-shot trend line.</p>
    </div>
    <div class="metric-chart-grid">
      <div class="card">
        <h3>Shooting percentage: early vs. late session</h3>
        <div id="trend-pct"></div>
      </div>
      ${notable.map((m) => `
        <div class="card">
          <h3>${m.label}</h3>
          <div id="trend-${m.metric_key}"></div>
        </div>`).join("")}
    </div>
  `;
  Charts.earlyLateLine(document.getElementById("trend-pct"), {
    early: t.early_shooting_pct, late: t.late_shooting_pct, unit: "%",
  });
  notable.forEach((m) => {
    Charts.earlyLateLine(document.getElementById(`trend-${m.metric_key}`), {
      early: m.early_mean, late: m.late_mean, unit: ` ${m.unit}`,
    });
  });
}

function renderReplay(data) {
  const container = document.getElementById("tab-replay");
  const hasAnnotated = data.has_annotated_video;
  const hasDiagnostic = data.has_diagnostic_video;
  if (!hasAnnotated && !hasDiagnostic) {
    container.innerHTML = `<div class="empty-state">Annotated replay is not available for this session.</div>`;
    return;
  }
  // Only offer the toggle when both variants genuinely exist -- a session
  // can have just one (rendering can partially fail locally, and the
  // public demo deliberately ships only the clean annotated cut, never
  // diagnostic.mp4) and offering a switch to a video that isn't there
  // would just produce a broken player.
  const showToggle = hasAnnotated && hasDiagnostic;
  container.innerHTML = `
    ${showToggle ? `
    <div class="mode-toggle">
      <button class="tab-btn active" id="replay-clean">Clean replay</button>
      <button class="tab-btn" id="replay-diag">Diagnostic mode</button>
    </div>` : ""}
    <div class="replay-wrap">
      <div class="replay-video"><video id="replay-video" controls preload="auto"></video></div>
      <div class="replay-side">
        <div class="card">
          <h3>Jump to shot</h3>
          <div class="shot-list">
            ${(data.shots || []).map((s) => `<div class="shot-chip" data-t="${s.start_time_sec}"><span class="n">#${s.shot_index}</span><span class="outcome-dot ${outcomeClass(displayOutcome(s))}"></span></div>`).join("")}
          </div>
        </div>
      </div>
    </div>
  `;
  const video = document.getElementById("replay-video");
  const setSrc = (kind) => { video.src = Api.videoUrl(data.session_id, kind); };
  setSrc(hasAnnotated ? "annotated" : "diagnostic");

  if (showToggle) {
    document.getElementById("replay-clean").addEventListener("click", (e) => {
      document.querySelectorAll(".mode-toggle .tab-btn").forEach((b) => b.classList.remove("active"));
      e.target.classList.add("active");
      setSrc("annotated");
    });
    document.getElementById("replay-diag").addEventListener("click", (e) => {
      document.querySelectorAll(".mode-toggle .tab-btn").forEach((b) => b.classList.remove("active"));
      e.target.classList.add("active");
      setSrc("diagnostic");
    });
  }
  container.querySelectorAll(".shot-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      seekReplayTo(video, Number(chip.dataset.t));
    });
  });
}

/* Setting video.currentTime before the browser knows the media's duration/
   seekable range (readyState < HAVE_METADATA) is silently dropped by the
   spec -- the seek never applies and playback starts from wherever the
   video already was (typically 0), which is why every "Jump to shot" click
   looked like it always landed on Shot 1: shot 1's own start time is close
   to 0, so a dropped seek was indistinguishable from a correct one only for
   that shot. Every other shot's seek was silently discarded the same way.
   No arbitrary delay is used -- readyState/loadedmetadata are the actual
   signal for "is a seek safe to apply yet". */
function seekReplayTo(video, timeSec) {
  if (Number.isNaN(timeSec)) return;
  const doSeek = () => { video.currentTime = timeSec; video.play(); };
  if (video.readyState >= HTMLMediaElement.HAVE_METADATA) {
    doSeek();
  } else {
    video.addEventListener("loadedmetadata", doSeek, { once: true });
  }
}

function simpleMarkdownToHtml(md) {
  return md
    .replace(/^### (.*)$/gm, "<h3>$1</h3>")
    .replace(/^## (.*)$/gm, "<h2>$1</h2>")
    .replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/^- (.*)$/gm, "<li>$1</li>")
    .replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`)
    .split(/\n{2,}/).map((block) => (/^<h\d|^<ul/.test(block.trim()) ? block : `<p>${block}</p>`)).join("\n");
}

let methodologyLoaded = false;
async function renderMethodology() {
  if (methodologyLoaded) return;
  try {
    const { markdown } = await Api.methodology();
    document.getElementById("tab-methodology-standalone").innerHTML = `<div class="methodology-body">${simpleMarkdownToHtml(markdown)}</div>`;
    methodologyLoaded = true;
  } catch (e) {
    document.getElementById("tab-methodology-standalone").innerHTML = `<div class="empty-state">Methodology document unavailable.</div>`;
  }
}

function initMethodologyView() {
  const cameFrom = { view: "landing" };
  document.getElementById("footer-methodology-link").addEventListener("click", () => {
    const active = document.querySelector(".view.active");
    cameFrom.view = active ? active.id.replace("view-", "") : "landing";
    switchView("methodology");
    renderMethodology();
  });
  document.getElementById("methodology-back-btn").addEventListener("click", () => switchView(cameFrom.view));
}

/* ---------------- History ---------------- */

function initHistory() {
  document.getElementById("nav-history").addEventListener("click", async () => {
    switchView("history");
    const list = document.getElementById("history-list");
    if (window.ARCVISION_MODE === "demo") {
      list.innerHTML = `<div class="empty-state">Session history isn't available in the public demo &mdash;` +
        ` it's a single precomputed session. Run ArcVision locally to build up your own session history.</div>`;
      return;
    }
    list.innerHTML = `<div class="empty-state">Loading&hellip;</div>`;
    try {
      const sessions = await Api.listSessions();
      if (!sessions.length) {
        list.innerHTML = `<div class="empty-state">No past sessions yet.</div>`;
        return;
      }
      list.innerHTML = sessions.map((s) => {
        const badgeClass = s.status === "completed" ? "high" : s.status === "processing" ? "medium" : "critical";
        const isTerminalError = s.status === "failed" || s.status === "interrupted";
        return `
        <div class="history-row" data-id="${s.session_id}" data-status="${s.status}">
          <div class="history-row-main">
            <span>${s.original_filename}</span>
            ${isTerminalError && s.error_message ? `<span class="history-row-error">${s.error_message}</span>` : ""}
          </div>
          <span style="color:var(--text-muted)">${new Date(s.created_at).toLocaleString()}</span>
          <span class="confidence-badge ${badgeClass}">${s.status}</span>
        </div>`;
      }).join("");
      list.querySelectorAll(".history-row").forEach((row) => {
        row.addEventListener("click", async () => {
          if (row.dataset.status !== "completed") return;
          const id = row.dataset.id;
          const results = await Api.results(id);
          currentResults = results;
          renderDashboard(results);
          switchView("dashboard");
        });
      });
    } catch (e) {
      list.innerHTML = `<div class="empty-state">Could not load session history.</div>`;
    }
  });
  document.getElementById("history-back-btn").addEventListener("click", () => switchView("landing"));
}

document.addEventListener("DOMContentLoaded", () => {
  initUpload();
  initTabs();
  initSubTabs();
  initHistory();
  initMethodologyView();
  initActiveJobIndicator();
  initDemoMode();
  resumeActiveSessionIfAny();
});
