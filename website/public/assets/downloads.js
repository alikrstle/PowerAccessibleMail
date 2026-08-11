const releaseApi =
  "https://api.github.com/repos/alikrstle/PowerAccessibleMail/releases/latest";

const releaseElements = {
  version: document.querySelectorAll("[data-release-version]"),
  date: document.querySelectorAll("[data-release-date]"),
  x64: document.querySelectorAll("[data-download-x64]"),
  x64Hash: document.querySelectorAll("[data-hash-x64]"),
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
    if (!x64) throw new Error("The x64 release installer is unavailable.");

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
    if (x64Hash) {
      releaseElements.x64Hash.forEach((element) => {
        element.href = x64Hash.browser_download_url;
      });
    }
    releaseElements.page.forEach((element) => {
      element.href = release.html_url;
    });
    setStatus(
      "تم التحقق من رابط إصدار 64 بت. نسخة 32 بت متوقفة مؤقتاً للصيانة.",
      "The 64-bit release link is confirmed. The 32-bit edition is temporarily unavailable for maintenance."
    );
  } catch {
    setStatus(
      "تعذر التحقق الآن. روابط الإصدار المنشور المحفوظة أدناه ما زالت متاحة.",
      "Live verification is unavailable. The saved published-release links remain available."
    );
  }
}

refreshRelease();
