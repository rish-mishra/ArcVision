const Api = {
  async upload(file) {
    if (window.ARCVISION_MODE === "demo") {
      // Defense in depth -- app.js intercepts before this is ever called
      // in demo mode and shows the polished explanation panel instead.
      // This exists so a direct call (or a future code path) never
      // silently attempts a network request that can't work on a static
      // host.
      throw new Error("Upload isn't available in the public demo.");
    }
    const form = new FormData();
    form.append("file", file);
    const resp = await fetch("/api/sessions/upload", { method: "POST", body: form });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = data.detail;
      const message = (detail && detail.message) ? detail.message : (typeof detail === "string" ? detail : "Upload failed.");
      throw new Error(message);
    }
    return data;
  },

  async status(sessionId) {
    const resp = await fetch(`/api/sessions/${sessionId}/status`);
    if (!resp.ok) throw new Error("Could not fetch status.");
    return resp.json();
  },

  async results(sessionId) {
    const resp = await fetch(`/api/sessions/${sessionId}/results`);
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      const detail = data.detail;
      throw new Error((detail && detail.message) || "Results not available.");
    }
    return data;
  },

  // The one bundled, genuinely-computed ArcVision session shipped with the
  // public demo -- see scripts/export_demo.py. Not sample/fabricated data:
  // a real export of a real analyzed session's stored results.
  async loadDemoSession() {
    const resp = await fetch("demo/session.json");
    if (!resp.ok) throw new Error("Demo session data could not be loaded.");
    return resp.json();
  },

  async listSessions() {
    if (window.ARCVISION_MODE === "demo") return [];
    const resp = await fetch("/api/sessions");
    if (!resp.ok) throw new Error("Could not load session history.");
    return resp.json();
  },

  async deleteSession(sessionId) {
    if (window.ARCVISION_MODE === "demo") return false;
    const resp = await fetch(`/api/sessions/${sessionId}`, { method: "DELETE" });
    return resp.ok;
  },

  async methodology() {
    if (window.ARCVISION_MODE === "demo") {
      const resp = await fetch("demo/methodology.md");
      if (!resp.ok) throw new Error("Methodology unavailable.");
      return { markdown: await resp.text() };
    }
    const resp = await fetch("/api/methodology");
    if (!resp.ok) throw new Error("Methodology unavailable.");
    return resp.json();
  },

  videoUrl(sessionId, kind) {
    if (window.ARCVISION_MODE === "demo") {
      // Only "annotated" is ever bundled with the public demo (see
      // docs/DEMO_DEPLOYMENT_AUDIT.md -- diagnostic.mp4 and raw source
      // video are deliberately never published), regardless of which kind
      // is requested.
      return "demo/annotated.mp4";
    }
    return `/api/sessions/${sessionId}/video/${kind}`;
  },
};
