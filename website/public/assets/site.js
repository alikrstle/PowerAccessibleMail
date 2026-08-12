const root = document.documentElement;
const languageButton = document.querySelector("[data-language-toggle]");
const languageLabel = document.querySelector("[data-language-label]");
const languageOptions = document.querySelector("[data-language-options]");
const themeOptions = document.querySelectorAll("[data-theme-option]");
const themeChoiceGroup = document.querySelector("[data-theme-choice-group]");

const copy = {
  ar: {
    languageLabel: "اختيار اللغة",
    languageText: "اللغة",
    themeLabel: "اختيار المظهر"
  },
  en: {
    languageLabel: "Choose language",
    languageText: "Language",
    themeLabel: "Choose theme"
  }
};

function currentLanguage() {
  return root.lang === "en" ? "en" : "ar";
}

function updateThemeOptions() {
  const dark = root.dataset.theme === "dark";
  themeOptions.forEach((option) => {
    option.checked = option.value === (dark ? "dark" : "light");
  });
}

function closeLanguageMenu() {
  if (!languageOptions || !languageButton) return;
  languageOptions.hidden = true;
  languageButton.setAttribute("aria-expanded", "false");
}

function setLanguage(language) {
  const selected = language === "en" ? "en" : "ar";
  root.lang = selected;
  root.dir = selected === "ar" ? "rtl" : "ltr";

  for (const element of document.querySelectorAll("[data-lang-content]")) {
    element.hidden = element.dataset.langContent !== selected;
  }

  if (languageButton) {
    languageButton.setAttribute("aria-label", copy[selected].languageLabel);
  }
  if (languageLabel) {
    languageLabel.textContent = copy[selected].languageText;
  }
  if (themeChoiceGroup) {
    themeChoiceGroup.setAttribute("aria-label", copy[selected].themeLabel);
  }
  for (const option of document.querySelectorAll("[data-language-option]")) {
    option.setAttribute("aria-pressed", String(option.dataset.languageOption === selected));
  }

  const titleSource = document.querySelector(`[data-page-title-${selected}]`);
  if (titleSource) {
    document.title = titleSource.getAttribute(`data-page-title-${selected}`);
  }

  for (const navigation of document.querySelectorAll(".site-nav")) {
    navigation.setAttribute(
      "aria-label",
      selected === "ar" ? "التنقل الرئيسي" : "Main navigation"
    );
  }
  for (const navigation of document.querySelectorAll(".footer-links")) {
    navigation.setAttribute(
      "aria-label",
      selected === "ar" ? "روابط قانونية" : "Legal links"
    );
  }

  localStorage.setItem("pam-language", selected);
  closeLanguageMenu();
  updateThemeOptions();
}

function setTheme(theme) {
  const selected = theme === "dark" ? "dark" : "light";
  root.dataset.theme = selected;
  localStorage.setItem("pam-theme", selected);
  updateThemeOptions();
}

const storedTheme = localStorage.getItem("pam-theme");
const preferredDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
setTheme(storedTheme === "dark" || (!storedTheme && preferredDark) ? "dark" : "light");
setLanguage(localStorage.getItem("pam-language") || "ar");

languageButton?.addEventListener("click", () => {
  if (!languageOptions) return;
  const opened = languageOptions.hidden;
  languageOptions.hidden = !opened;
  languageButton.setAttribute("aria-expanded", String(opened));
});

for (const option of document.querySelectorAll("[data-language-option]")) {
  option.addEventListener("click", () => {
    setLanguage(option.dataset.languageOption);
  });
}

themeOptions.forEach((option) => {
  option.addEventListener("change", () => {
    if (option.checked) {
      setTheme(option.value);
      return;
    }
    updateThemeOptions();
  });
});

document.addEventListener("click", (event) => {
  if (!languageButton || !languageOptions) return;
  const target = event.target;
  if (target instanceof Node && !languageButton.contains(target) && !languageOptions.contains(target)) {
    closeLanguageMenu();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    closeLanguageMenu();
  }
});
