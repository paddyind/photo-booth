const fs = require("fs");
const path = require("path");

const repoRoot = path.resolve(__dirname, "../../..");
const templateIndex = path.join(repoRoot, "apps/web/src/index.html");
const outDir = path.join(__dirname, "..", "www");
const outIndex = path.join(outDir, "index.html");

const apiBase = process.env.PHOTOBOOTH_API_BASE || "";
const hasEnable8x11Env = Object.prototype.hasOwnProperty.call(
  process.env,
  "PHOTOBOOTH_ENABLE_8X11"
);
const enable8x11Raw = (process.env.PHOTOBOOTH_ENABLE_8X11 || "").toLowerCase();
const enable8x11 =
  ["1", "true", "yes", "y", "on"].includes(enable8x11Raw) && hasEnable8x11Env;

// Mobile save: PHOTOBOOTH_SAVE_PATH = parent under fs_directory (e.g. Download, Documents).
// App always appends a persisted dated folder PhotoBooth_YYYYMMDD for originals + finals.
const fsDirectory = process.env.PHOTOBOOTH_FS_DIRECTORY || "EXTERNAL_STORAGE";
const hasSavePathEnv = Object.prototype.hasOwnProperty.call(
  process.env,
  "PHOTOBOOTH_SAVE_PATH"
);
const savePath = hasSavePathEnv
  ? String(process.env.PHOTOBOOTH_SAVE_PATH || "")
  : "Download";

if (!fs.existsSync(templateIndex)) {
  console.error(`Template index.html not found at: ${templateIndex}`);
  process.exit(1);
}

fs.mkdirSync(outDir, { recursive: true });

let html = fs.readFileSync(templateIndex, "utf8");

const scriptTagParts = [];

if (apiBase.trim()) {
  // Inject API base override for mobile testing.
  // The web app reads `window.PHOTOBOOTH_API_BASE` when present.
  scriptTagParts.push(
    `window.PHOTOBOOTH_API_BASE=${JSON.stringify(apiBase.trim())};`
  );
}

if (hasEnable8x11Env) {
  // Opt-in to showing 8x11 in the UI (default is hidden).
  scriptTagParts.push(`window.PHOTOBOOTH_ENABLE_8X11=${enable8x11 ? "true" : "false"};`);
}

// Always inject save paths for mobile www (defaults align with apps/web/src/index.html).
scriptTagParts.push(
  `window.PHOTOBOOTH_FS_DIRECTORY=${JSON.stringify(fsDirectory)};`
);
scriptTagParts.push(`window.PHOTOBOOTH_SAVE_PATH=${JSON.stringify(savePath)};`);

if (scriptTagParts.length > 0) {
  const scriptTag = `<script>${scriptTagParts.join("")}</script>`;
  html = html.replace("<head>", `<head>${scriptTag}`);
}

fs.writeFileSync(outIndex, html, "utf8");

console.log(
  `Prepared mobile www at ${outIndex}` +
    `${apiBase.trim() ? ` (apiBase=${apiBase.trim()})` : ""}` +
    `${hasEnable8x11Env ? ` (enable8x11=${enable8x11 ? "true" : "false"})` : ""}` +
    ` (fsDirectory=${fsDirectory}, savePath=${savePath})`
);

