const releaseTag = "v1.2.15";
const releaseApi =
  `https://api.github.com/repos/alikrstle/PowerAccessibleMail/releases/tags/${releaseTag}`;

const releaseElements = {
  version: document.querySelectorAll("[data-release-version]"),
  date: document.querySelectorAll("[data-release-date]"),
  x64: document.querySelectorAll("[data-download-x64]"),
  x64Hash: document.querySelectorAll("[data-hash-x64]"),
  x86: document.querySelectorAll("[data-download-x86]"),
  x86Hash: document.querySelectorAll("[data-hash-x86]"),
  page: document.querySelectorAll("[data-release-page]"),
  status: document.querySelectorAll("[data-release-status]")
};

function releaseAsset(assets, architecture) {
  const marker = architecture === "x64" ? "win-x64" : "win-x86";
  return assets.find(
    (asset) => asset.name.includes(marker) && asset.name.endsWith(".exe")
  );
}

function releaseHashAsset(assets, architecture) {
  const marker = architecture.toUpperCase();
  return assets.find(
    (asset) =>
      asset.name.startsWith(`SHA256SUMS-${marker}-`) &&
      asset.name.endsWith(".txt")
  );
}

function formatDate(date, language) {
  return new Intl.DateTimeFormat(language === "ar" ? "ar-IQ" : "en-US", {
    year: "numeric",
    month: "long",
    day: "numeric"
  }).format(date);
}

function setStatus(arabic, english) {
  releaseElements.status.forEach((element) => {
    const language = element.closest('[data-lang-content="en"]') ? "en" : "ar";
    element.textContent = language === "en" ? english : arabic;
  });
}

async function refreshRelease() {
  try {
    const response = await fetch(releaseApi, {
      cache: "no-store",
      headers: { Accept: "application/vnd.github+json" }
    });
    if (!response.ok) throw new Error(`GitHub returned ${response.status}`);

    const release = await response.json();
    const x64 = releaseAsset(release.assets, "x64");
    const x64Hash = releaseHashAsset(release.assets, "x64");
    const x86 = releaseAsset(release.assets, "x86");
    const x86Hash = releaseHashAsset(release.assets, "x86");
    if (release.draft || release.prerelease || !x64 || !x86 || !x64Hash || !x86Hash) {
      throw new Error("The stable release assets are incomplete.");
    }

    const version = release.tag_name.replace(/^v/, "");
    const published = new Date(release.published_at);

    releaseElements.version.forEach((element) => {
      element.textContent = version;
    });
    releaseElements.date.forEach((element) => {
      const language = element.closest('[lang="en"]') ? "en" : "ar";
      element.textContent = formatDate(published, language);
    });
    releaseElements.x64.forEach((element) => {
      element.href = x64.browser_download_url;
    });
    releaseElements.x64Hash.forEach((element) => {
      element.href = x64Hash.browser_download_url;
    });
    releaseElements.x86.forEach((element) => {
      element.href = x86.browser_download_url;
    });
    releaseElements.x86Hash.forEach((element) => {
      element.href = x86Hash.browser_download_url;
    });
    releaseElements.page.forEach((element) => {
      element.href = release.html_url;
    });
    setStatus(
      "تم التحقق من روابط الإصدار المستقر لنسختي 64 بت و32 بت.",
      "The x64 and x86 stable release links are confirmed."
    );
  } catch {
    setStatus(
      "تعذر التحقق الآن. روابط الإصدار المنشور المحفوظة أدناه ما زالت متاحة.",
      "Live verification is unavailable. The saved published-release links remain available."
    );
  }
}

refreshRelease();
