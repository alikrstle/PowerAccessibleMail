import { readFile } from "node:fs/promises";

const downloadsPage = await readFile(
  new URL("../public/downloads.html", import.meta.url),
  "utf8"
);
const headers = await readFile(new URL("../public/_headers", import.meta.url), "utf8");

const requiredMarkup = [
  '<h1 id="installer-downloads-ar">النسخ المثبتة</h1>',
  '<h2 id="portable-downloads-ar">تنزيل النسخ المحمولة</h2>',
  '<h1 id="installer-downloads-en">Installer editions</h1>',
  '<h2 id="portable-downloads-en">Download portable editions</h2>',
  "data-download-x64-installer",
  "data-download-x86-installer",
  "data-download-x64-portable",
  "data-download-x86-portable",
  "data-hash-x64",
  "data-hash-x86"
];

for (const expected of requiredMarkup) {
  if (!downloadsPage.includes(expected)) {
    throw new Error(`The download page is missing required markup: ${expected}`);
  }
}

for (const requiredHeader of [
  "Content-Security-Policy:",
  "Strict-Transport-Security:",
  "Permissions-Policy:",
  "X-Content-Type-Options: nosniff",
  "X-Frame-Options: DENY"
]) {
  if (!headers.includes(requiredHeader)) {
    throw new Error(`The Cloudflare header policy is missing: ${requiredHeader}`);
  }
}

console.log("Download headings, release choices, and Cloudflare security headers are complete.");
