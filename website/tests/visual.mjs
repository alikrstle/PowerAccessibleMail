import { access, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium } from "playwright-core";

const candidates = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"
];

let executablePath;
for (const candidate of candidates) {
  try {
    await access(candidate);
    executablePath = candidate;
    break;
  } catch {
    // Try the next installed browser.
  }
}

if (!executablePath) {
  throw new Error("Chrome or Microsoft Edge is required for visual tests.");
}

const output = resolve(import.meta.dirname, "..", "test-results");
await mkdir(output, { recursive: true });

const browser = await chromium.launch({ executablePath, headless: true });
try {
  for (const viewport of [
    { name: "desktop", width: 1440, height: 900 },
    { name: "mobile", width: 390, height: 844 }
  ]) {
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
      reducedMotion: "reduce"
    });
    await page.goto("http://127.0.0.1:4173/index.html", {
      waitUntil: "networkidle"
    });
    await page.screenshot({
      path: resolve(output, `homepage-${viewport.name}.png`),
      fullPage: true
    });

    await page.goto("http://127.0.0.1:4173/downloads.html", {
      waitUntil: "networkidle"
    });
    await page.screenshot({
      path: resolve(output, `downloads-${viewport.name}.png`),
      fullPage: true
    });
    await page.close();
  }
} finally {
  await browser.close();
}

console.log(`Saved visual checks in ${output}`);
