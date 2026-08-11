import { readFile } from "node:fs/promises";

const repository = "alikrstle/PowerAccessibleMail";
const apiUrl = `https://api.github.com/repos/${repository}/releases/latest`;
const downloadsPage = await readFile(new URL("../public/downloads.html", import.meta.url), "utf8");

const response = await fetch(apiUrl, {
  headers: {
    Accept: "application/vnd.github+json",
    "User-Agent": "PowerAccessibleMail-Website-release-check"
  }
});

if (!response.ok) {
  throw new Error(`GitHub release lookup failed with HTTP ${response.status}.`);
}

const release = await response.json();
const version = String(release.tag_name ?? "").replace(/^v/, "");
const assets = Array.isArray(release.assets) ? release.assets : [];
const installer = assets.find(
  (asset) => asset.name.includes("win-x64") && asset.name.endsWith(".exe")
);
const checksums = assets.find(
  (asset) => asset.name.startsWith("SHA256SUMS-X64-") && asset.name.endsWith(".txt")
);

if (!version || !installer || !checksums) {
  throw new Error("The latest release must provide an x64 installer and SHA-256 file.");
}

for (const expected of [release.html_url, installer.browser_download_url, checksums.browser_download_url]) {
  if (!downloadsPage.includes(expected)) {
    throw new Error(`downloads.html fallback is out of date: ${expected}`);
  }
}

console.log(`Release ${release.tag_name} is correctly linked (${assets.length} assets).`);
