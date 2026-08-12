import { readFile } from "node:fs/promises";
import { chromium } from "playwright-core";

const chromePaths = [
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
  "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"
];

const { access } = await import("node:fs/promises");
let executablePath;
for (const candidate of chromePaths) {
  try {
    await access(candidate);
    executablePath = candidate;
    break;
  } catch {
    // Try the next installed browser.
  }
}

if (!executablePath) {
  throw new Error("Chrome or Microsoft Edge is required for accessibility tests.");
}

const axeSource = await readFile(
  new URL("../node_modules/axe-core/axe.min.js", import.meta.url),
  "utf8"
);

const pages = [
  "index.html",
  "downloads.html",
  "privacy.html",
  "terms.html",
  "support.html",
  "accessibility.html"
];

const viewports = [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 }
];

const browser = await chromium.launch({ executablePath, headless: true });
let failures = 0;

async function selectLanguage(page, language) {
  if ((await page.locator("html").getAttribute("lang")) === language) return;

  await page.locator("[data-language-toggle]").click();
  await page.locator(`[data-language-option="${language}"]`).click();
}

try {
  for (const viewport of viewports) {
    const context = await browser.newContext({
      viewport: { width: viewport.width, height: viewport.height },
      reducedMotion: "reduce"
    });

    for (const pageName of pages) {
      const page = await context.newPage();
      const pageErrors = [];
      page.on("pageerror", (error) => {
        pageErrors.push(error.message);
      });
      const response = await page.goto(`http://127.0.0.1:4173/${pageName}`, {
        waitUntil: "networkidle"
      });

      if (!response?.ok()) {
        console.error(`${pageName} (${viewport.name}): HTTP ${response?.status()}`);
        failures += 1;
        await page.close();
        continue;
      }

      await selectLanguage(page, "ar");

      await page.addScriptTag({ content: axeSource });
      for (const language of ["ar", "en"]) {
        await selectLanguage(page, language);

        const result = await page.evaluate(async () => {
          return window.axe.run(document, {
            runOnly: {
              type: "tag",
              values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]
            }
          });
        });

        if (result.violations.length > 0) {
          failures += result.violations.length;
          console.error(
            `${pageName} (${viewport.name}, ${language}) accessibility violations:`
          );
          for (const violation of result.violations) {
            console.error(`- ${violation.id}: ${violation.help}`);
          }
        } else {
          console.log(`${pageName} (${viewport.name}, ${language}): passed`);
        }
      }

      if (pageErrors.length > 0) {
        console.error(`${pageName} (${viewport.name}) JavaScript errors:`);
        for (const error of pageErrors) {
          console.error(`- ${error}`);
        }
        failures += pageErrors.length;
      }

      const overflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth;
      });
      if (overflow) {
        console.error(`${pageName} (${viewport.name}): horizontal overflow`);
        failures += 1;
      }

      await page.close();
    }

    await context.close();
  }
} finally {
  await browser.close();
}

if (failures > 0) {
  throw new Error(`Accessibility validation failed with ${failures} issue(s).`);
}
