const releaseTag = "v1.3.1";
const releaseApi =
  `https://api.github.com/repos/alikrstle/PowerAccessibleMail/releases/tags/${releaseTag}`;

const releaseElements = {
  version: document.querySelectorAll("[data-release-version]"),
  date: document.querySelectorAll("[data-release-date]"),
  x64Installer: document.querySelectorAll("[data-download-x64-installer]"),
  x64Portable: document.querySelectorAll("[data-download-x64-portable]"),
  x64Hash: document.querySelectorAll("[data-hash-x64]"),
  x86Installer: document.querySelectorAll("[data-download-x86-installer]"),
  x86Portable: document.querySelectorAll("[data-download-x86-portable]"),
  x86Hash: document.querySelectorAll("[data-hash-x86]"),
  page: document.querySelectorAll("[data-release-page]"),
  status: document.querySelectorAll("[data-release-status]")
};

function releaseAsset(assets, architecture, extension) {
  const marker = architecture === "x64" ? "win-x64" : "win-x86";
  return assets.find(
    (asset) => asset.name.includes(marker) && asset.name.endsWith(extension)
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
    const x64Installer = releaseAsset(release.assets, "x64", ".exe");
    const x64Portable = releaseAsset(release.assets, "x64", ".zip");
    const x64Hash = releaseHashAsset(release.assets, "x64");
    const x86Installer = releaseAsset(release.assets, "x86", ".exe");
    const x86Portable = releaseAsset(release.assets, "x86", ".zip");
    const x86Hash = releaseHashAsset(release.assets, "x86");
    if (release.draft || release.prerelease || !x64Installer || !x64Portable || !x86Installer || !x86Portable || !x64Hash || !x86Hash) {
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
    releaseElements.x64Installer.forEach((element) => {
      element.href = x64Installer.browser_download_url;
    });
    releaseElements.x64Portable.forEach((element) => {
      element.href = x64Portable.browser_download_url;
    });
    releaseElements.x64Hash.forEach((element) => {
      element.href = x64Hash.browser_download_url;
    });
    releaseElements.x86Installer.forEach((element) => {
      element.href = x86Installer.browser_download_url;
    });
    releaseElements.x86Portable.forEach((element) => {
      element.href = x86Portable.browser_download_url;
    });
    releaseElements.x86Hash.forEach((element) => {
      element.href = x86Hash.browser_download_url;
    });
    releaseElements.page.forEach((element) => {
      element.href = release.html_url;
    });
    setStatus(
      "تم التحقق من روابط المثبت والنسخة المحمولة لإصداري 64 بت و32 بت.",
      "The x64 and x86 installer and portable links are confirmed."
    );
  } catch {
    setStatus(
      "تعذر التحقق الآن. روابط الإصدار المنشور المحفوظة أدناه ما زالت متاحة.",
      "Live verification is unavailable. The saved published-release links remain available."
    );
  }
}

refreshRelease();
