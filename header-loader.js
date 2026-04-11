/**
 * PwaniStays — header-loader.js
 * ================================
 * Fetches /header.html and injects it into <div id="site-header">.
 * Also activates the correct nav link, wires up the mobile menu,
 * dropdown toggles, header search, and the language switcher.
 *
 * HOW TO USE ON ANY PAGE
 * ─────────────────────────────────────────────────────────────
 * 1. In <head> (BEFORE any other scripts):
 *      <script src="/i18n.js"></script>
 *
 * 2. In <head> — add the shared header CSS:
 *      <link rel="stylesheet" href="/header.css">
 *
 * 3. In <body>, at the very top (before page content):
 *      <div id="site-header"></div>
 *
 * 4. At the BOTTOM of <body> (after Font Awesome):
 *      <script src="/header-loader.js"></script>
 *
 * That's it. The header renders itself, detects the language,
 * marks the right nav link active, and everything works.
 * ─────────────────────────────────────────────────────────────
 */

(async function () {
  const HEADER_URL = "/header.html";

  // ── 1. Fetch the shared header HTML ──────────────────────
  async function fetchHeader() {
    try {
      const res = await fetch(HEADER_URL, { cache: "no-cache" });
      if (!res.ok) throw new Error("Header fetch failed: " + res.status);
      return await res.text();
    } catch (e) {
      console.warn("[header-loader] Could not load header.html:", e);
      return null;
    }
  }

  // ── 2. Determine which page we're on ─────────────────────
  function getCurrentPage() {
    const path = window.location.pathname
      .replace(/\/$/, "")        // strip trailing slash
      .replace(/\.html$/, "")    // strip .html
      .split("/")
      .filter(Boolean)
      .pop() || "home";
    return path;
  }

  // ── 3. Mark the active nav link ──────────────────────────
  function markActiveLink(container) {
    const page = getCurrentPage();
    container.querySelectorAll("[data-nav-page]").forEach((el) => {
      if (el.getAttribute("data-nav-page") === page) {
        el.classList.add("active");
        // If inside a dropdown, also highlight the parent
        const parentDropdown = el.closest(".dropdown");
        if (parentDropdown) {
          parentDropdown.querySelector(".dropdown-toggle")?.classList.add("active");
        }
      } else {
        el.classList.remove("active");
      }
    });
    // Home page: mark home link active when path is "/" or "/index"
    if (page === "home" || page === "index" || window.location.pathname === "/") {
      container.querySelectorAll('[data-nav-page="home"]').forEach((el) =>
        el.classList.add("active")
      );
    }
  }

  // ── 4. Wire up mobile menu toggle ────────────────────────
  function initMobileMenu(container) {
    const menuToggle = container.querySelector(".menu-toggle");
    const navLinks = container.querySelector(".nav-links");
    const dropdownToggles = container.querySelectorAll(".dropdown > a");

    if (!menuToggle || !navLinks) return;

    menuToggle.addEventListener("click", function () {
      navLinks.classList.toggle("active");
      const isExpanded = this.getAttribute("aria-expanded") === "true";
      this.setAttribute("aria-expanded", !isExpanded);
    });

    // Close menu when clicking a non-dropdown link
    container.querySelectorAll(".nav-links a:not(.dropdown > a)").forEach((link) => {
      link.addEventListener("click", () => {
        if (!link.getAttribute("href")?.startsWith("#")) return;
        navLinks.classList.remove("active");
        menuToggle.setAttribute("aria-expanded", "false");
      });
    });

    // Dropdown toggles on mobile / tablet
    dropdownToggles.forEach((toggle) => {
      toggle.addEventListener("click", function (e) {
        if (window.innerWidth <= 992) {
          e.preventDefault();
          const parent = this.parentElement;
          parent.classList.toggle("active");
          dropdownToggles.forEach((other) => {
            const otherParent = other.parentElement;
            if (otherParent !== parent && otherParent.classList.contains("active")) {
              otherParent.classList.remove("active");
            }
          });
        }
      });
    });

    // Close dropdowns on outside click (desktop)
    document.addEventListener("click", function (e) {
      if (window.innerWidth > 992) {
        container.querySelectorAll(".dropdown").forEach((dd) => {
          if (!dd.contains(e.target)) dd.classList.remove("active");
        });
      }
    });
  }

  // ── 5. Wire up header search ──────────────────────────────
  function initHeaderSearch(container) {
    const searchContainer = container.querySelector(".header-search-container");
    const searchToggle = container.querySelector("#searchToggle");
    const searchInput = container.querySelector("#headerSearch");

    if (!searchToggle || !searchContainer || !searchInput) return;

    searchToggle.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      searchContainer.classList.toggle("active");
      if (searchContainer.classList.contains("active")) {
        setTimeout(() => searchInput.focus(), 50);
      }
    });

    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const term = searchInput.value.trim();
        if (term) {
          // If we're on the home page, trigger search directly
          if (typeof window.performKeywordSearch === "function") {
            window.performKeywordSearch(term);
          } else {
            // Navigate to home with search query
            window.location.href = `/?search=${encodeURIComponent(term)}`;
          }
        }
      }
    });

    // Close on outside click
    document.addEventListener("click", (e) => {
      if (
        window.innerWidth > 768 &&
        !searchContainer.contains(e.target) &&
        e.target !== searchToggle &&
        e.target !== searchInput
      ) {
        searchContainer.classList.remove("active");
      }
    });
  }

  // ── 6. Language switcher (delegated events, no inline onclick) ──
  const LANGUAGES = [
    { code: "en", label: "EN", name: "English",    flag: "🇬🇧" },
    { code: "no", label: "NO", name: "Norsk",       flag: "🇳🇴" },
    { code: "da", label: "DA", name: "Dansk",       flag: "🇩🇰" },
    { code: "pl", label: "PL", name: "Polski",      flag: "🇵🇱" },
    { code: "sv", label: "SV", name: "Svenska",     flag: "🇸🇪" },
    { code: "fi", label: "FI", name: "Suomi",       flag: "🇫🇮" },
    { code: "de", label: "DE", name: "Deutsch",     flag: "🇩🇪" },
    { code: "nl", label: "NL", name: "Nederlands",  flag: "🇳🇱" },
    { code: "fr", label: "FR", name: "Français",    flag: "🇫🇷" },
    { code: "is", label: "IS", name: "Íslenska",    flag: "🇮🇸" },
  ];

  // Delegated click handler for language options
  function handleLanguageOptionClick(e) {
    const option = e.target.closest(".lang-option");
    if (!option) return;

    const langCode = option.dataset.lang;
    if (!langCode) return;

    // Call setLanguage if available; otherwise wait and retry
    if (typeof window.setLanguage === "function") {
      window.setLanguage(langCode);
    } else if (window.i18n && typeof window.i18n.setLanguage === "function") {
      window.i18n.setLanguage(langCode);
    } else {
      console.warn("[header-loader] setLanguage not ready, retrying...");
      setTimeout(() => {
        if (typeof window.setLanguage === "function") window.setLanguage(langCode);
      }, 200);
    }

    // Close dropdown
    const dropdown = document.getElementById("langDropdown");
    const btn = document.getElementById("langCurrentBtn");
    if (dropdown) dropdown.classList.remove("open");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  // Toggle dropdown when clicking the current language button
  function handleToggleClick(e) {
    const btn = e.target.closest("#langCurrentBtn");
    if (!btn) return;
    const dropdown = document.getElementById("langDropdown");
    if (dropdown) {
      const isOpen = dropdown.classList.toggle("open");
      btn.setAttribute("aria-expanded", isOpen);
    }
  }

  // Close dropdown when clicking outside
  function handleOutsideClick(e) {
    const switcher = document.getElementById("langSwitcher");
    if (!switcher) return;
    if (!switcher.contains(e.target)) {
      const dropdown = document.getElementById("langDropdown");
      const btn = document.getElementById("langCurrentBtn");
      if (dropdown) dropdown.classList.remove("open");
      if (btn) btn.setAttribute("aria-expanded", "false");
    }
  }

  function buildSwitcher(container) {
    const switcherEl = container.querySelector("#langSwitcher");
    if (!switcherEl) return;

    let activeLang = "en";
    try { activeLang = localStorage.getItem("pwani_lang") || "en"; } catch (_) {}
    if (window.i18n) activeLang = window.i18n.getCurrentLang();

    const current = LANGUAGES.find((l) => l.code === activeLang) || LANGUAGES[0];

    switcherEl.innerHTML = `
      <div class="lang-current" id="langCurrentBtn" role="button" tabindex="0"
           aria-haspopup="listbox" aria-expanded="false">
        <span class="lang-flag">${current.flag}</span>
        <span class="lang-code">${current.label}</span>
        <span class="lang-arrow">▾</span>
      </div>
      <ul class="lang-dropdown" id="langDropdown" role="listbox">
        ${LANGUAGES.map((lang) => `
          <li role="option"
              class="lang-option ${lang.code === activeLang ? "active" : ""}"
              data-lang="${lang.code}"
              aria-selected="${lang.code === activeLang}">
            <span class="lang-flag">${lang.flag}</span>
            <span class="lang-name">${lang.name}</span>
          </li>`).join("")}
      </ul>`;

    // Attach global delegated listeners (only once)
    if (!window._langSwitcherListenersAttached) {
      document.addEventListener("click", handleLanguageOptionClick);
      document.addEventListener("click", handleToggleClick);
      document.addEventListener("click", handleOutsideClick);
      window._langSwitcherListenersAttached = true;
    }
  }

  // ── 7. Expose a global toggle for compatibility (used by keyboard etc.) ──
  window.toggleLangDropdown = function () {
    const dropdown = document.getElementById("langDropdown");
    const btn = document.getElementById("langCurrentBtn");
    if (!dropdown) return;
    const isOpen = dropdown.classList.toggle("open");
    btn?.setAttribute("aria-expanded", isOpen);
  };

  // ── 8. Handle incoming ?search= query param on home page ─
  function handleSearchParam() {
    if (window.location.pathname !== "/" && !window.location.pathname.endsWith("index.html")) return;
    const params = new URLSearchParams(window.location.search);
    const term = params.get("search");
    if (term && typeof window.performKeywordSearch === "function") {
      // Wait for Supabase to be ready
      setTimeout(() => window.performKeywordSearch(term), 1000);
    }
  }

  // ── 9. Main: inject header and initialise everything ─────
  async function init() {
    const container = document.getElementById("site-header");
    if (!container) {
      console.warn("[header-loader] No #site-header element found on this page.");
      return;
    }

    const headerHTML = await fetchHeader();
    if (!headerHTML) return;

    container.innerHTML = headerHTML;

    // Grab the injected header element
    const headerEl = container.querySelector("header");

    markActiveLink(container);
    initMobileMenu(container);
    initHeaderSearch(container);
    buildSwitcher(container);

    // Apply i18n translations once i18n.js is ready
    if (window.i18n) {
      window.i18n.applyStaticTranslations?.();
    } else {
      // Poll briefly in case i18n.js is still detecting language
      let attempts = 0;
      const poll = setInterval(() => {
        attempts++;
        if (window.i18n) {
          window.i18n.applyStaticTranslations?.();
          buildSwitcher(container); // rebuild with detected lang
          clearInterval(poll);
        }
        if (attempts > 20) clearInterval(poll);
      }, 150);
    }

    handleSearchParam();
  }

  // Run after DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
