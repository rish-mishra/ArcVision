/* ArcVision environment config -- loaded before api.js/app.js.

   ARCVISION_MODE:
     "local" (default, as shipped in this repo) -- the real upload/History/
     processing flow against a live FastAPI backend, unchanged.
     "demo" -- set ONLY in the exported static bundle produced by
     scripts/export_demo.py (see docs/DEMO_DEPLOYMENT_AUDIT.md). Never hand
     -edit this value to test demo mode against a live local backend --
     instead run the export script and serve its output directory
     separately, so you're previewing the exact thing that would be
     published.

   ARCVISION_REPO_URL:
     The public GitHub repository URL, used only for the two "learn more"
     links shown by demo mode's upload-explanation panel. Left empty here
     on purpose -- fill in once the repository is public; the UI degrades
     gracefully (omits the links) while empty rather than pointing anywhere
     guessed. */
window.ARCVISION_MODE = "local";
window.ARCVISION_REPO_URL = "";
