import { readFile } from "node:fs/promises";

const repository = "alikrstle/PowerAccessibleMail";
const releaseTag = "v1.3.1";
const apiUrl = `https://api.github.com/repos/${repository}/releases/tags/${releaseTag}`;
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
function releaseAsset(architecture, extension) {
  return assets.find(
    (asset) => asset.name.includes(`win-${architecture}`) && asset.name.endsWith(extension)
  );
}

function checksumAsset(architecture) {
  return assets.find(
    (asset) =>
      asset.name.startsWith(`SHA256SUMS-${architecture.toUpperCase()}-`) &&
      asset.name.endsWith(".txt")
  );
}

const x64Installer = releaseAsset("x64", ".exe");
const x64Portable = releaseAsset("x64", ".zip");
const x86Installer = releaseAsset("x86", ".exe");
const x86Portable = releaseAsset("x86", ".zip");
const x64Checksums = checksumAsset("x64");
const x86Checksums = checksumAsset("x86");

if (
  release.tag_name !== releaseTag ||
  release.draft ||
  release.prerelease ||
  !version ||
  !x64Installer ||
  !x64Portable ||
  !x86Installer ||
  !x86Portable ||
  !x64Checksums ||
  !x86Checksums
) {
  throw new Error("The stable release must provide x64 and x86 installers, portable ZIP files, and SHA-256 files.");
}

for (const expected of [
  release.html_url,
  x64Installer.browser_download_url,
  x64Portable.browser_download_url,
  x86Installer.browser_download_url,
  x86Portable.browser_download_url,
  x64Checksums.browser_download_url,
  x86Checksums.browser_download_url
]) {
  if (!downloadsPage.includes(expected)) {
    throw new Error(`downloads.html fallback is out of date: ${expected}`);
  }
}

console.log(`Release ${release.tag_name} is correctly linked (${assets.length} assets).`);
