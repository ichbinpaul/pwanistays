/**
 * PwaniStays — header-loader.js (FIXED)
 * =======================================
 * Key fixes:
 * 1. Language dropdown uses addEventListener instead of inline onclick
 *    attributes — eliminates the global scope timing race condition.
 * 2. Dropdown is appended to <body> and positioned absolutely relative
 *    to the switcher button via getBoundingClientRect() — guarantees it
 *    is never clipped by any parent overflow or stacking context.
 * 3. setLanguage / toggleLangDropdown still exposed as globals for
 *    backward compatibility, but the real listeners are DOM-based.
 */

(async function () {
  const HEADER_URL = "/header.html";

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

  // ── Floating dropdown — appended to <body> so it is never clipped ──
  let floatingDropdown = null;
  let dropdownOpen = false;

  function getCurrentLang() {
    if (window.i18n) return window.i18n.getCurrentLang();
    try { return localStorage.getItem("pwani_lang") || "en"; } catch (_) { return "en"; }
  }

  // ── Build and attach the floating dropdown to <body> ──────────────
  function createFloatingDropdown() {
    if (floatingDropdown) floatingDropdown.remove();

    const activeLang = getCurrentLang();
    const ul = document.createElement("ul");
    ul.id = "langDropdownFloating";
    ul.setAttribute("role", "listbox");
    ul.setAttribute("aria-label", "Select language");

    LANGUAGES.forEach((lang) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", lang.code === activeLang);
      li.className = "lang-option" + (lang.code === activeLang ? " active" : "");
      li.innerHTML = `<span class="lang-flag">${lang.flag}</span><span class="lang-name">${lang.name}</span>`;

      // addEventListener — no inline onclick, no global scope race
      li.addEventListener("click", (e) => {
        e.stopPropagation();
        handleSetLanguage(lang.code);
      });

      ul.appendChild(li);
    });

    // Inline critical styles so they work regardless of CSS load order
    Object.assign(ul.style, {
      position:    "fixed",
      background:  "white",
      borderRadius:"10px",
      boxShadow:   "0 8px 25px rgba(0,0,0,0.18)",
      padding:     "6px 0",
      minWidth:    "160px",
      listStyle:   "none",
      zIndex:      "99999",
      display:     "none",
      margin:      "0",
    });

    document.body.appendChild(ul);
    floatingDropdown = ul;
  }

  // ── Position the dropdown next to the trigger button ─────────────
  function positionDropdown(triggerEl) {
    if (!floatingDropdown) return;
    const rect   = triggerEl.getBoundingClientRect();
    const dropH  = floatingDropdown.offsetHeight || 340;
    const spaceBelow = window.innerHeight - rect.bottom;

    if (spaceBelow < dropH && rect.top > dropH) {
      floatingDropdown.style.top = (rect.top - dropH - 4) + "px";
    } else {
      floatingDropdown.style.top = (rect.bottom + 4) + "px";
    }

    let left = rect.right - 160;
    if (left < 8) left = 8;
    floatingDropdown.style.left = left + "px";
  }

  // ── Open / close ──────────────────────────────────────────────────
  function openDropdown(triggerEl) {
    if (!floatingDropdown) createFloatingDropdown();
    floatingDropdown.style.display = "block";
    positionDropdown(triggerEl);
    dropdownOpen = true;
    triggerEl.setAttribute("aria-expanded", "true");
  }

  function closeDropdown() {
    if (floatingDropdown) floatingDropdown.style.display = "none";
    dropdownOpen = false;
    const btn = document.getElementById("langCurrentBtn");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  // ── Set language ──────────────────────────────────────────────────
  async function handleSetLanguage(langCode) {
    closeDropdown();
    if (window.i18n) {
      // setLanguage handles: applyStaticTranslations + translatePageBody + property cards
      await window.i18n.setLanguage(langCode);
    } else {
      try { localStorage.setItem("pwani_lang", langCode); } catch (_) {}
    }
    // Rebuild the switcher button to show new flag/code
    rebuildSwitcherButton();
  }

  // ── Build the trigger button (not the dropdown list) ─────────────
  function rebuildSwitcherButton() {
    const switcherEl = document.getElementById("langSwitcher");
    if (!switcherEl) return;

    const activeLang = getCurrentLang();
    const current = LANGUAGES.find((l) => l.code === activeLang) || LANGUAGES[0];

    switcherEl.innerHTML = `
      <div class="lang-current" id="langCurrentBtn"
           role="button" tabindex="0"
           aria-haspopup="listbox" aria-expanded="false">
        <span class="lang-flag">${current.flag}</span>
        <span class="lang-code">${current.label}</span>
        <span class="lang-arrow">▾</span>
      </div>`;

    const btn = switcherEl.querySelector("#langCurrentBtn");

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (dropdownOpen) {
        closeDropdown();
      } else {
        createFloatingDropdown();
        openDropdown(btn);
      }
    });

    btn.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); btn.click(); }
      if (e.key === "Escape") closeDropdown();
    });
  }

  // ── Global stubs (backward-compat for any inline onclick in HTML) ─
  window.toggleLangDropdown = function () {
    const btn = document.getElementById("langCurrentBtn");
    if (!btn) return;
    if (dropdownOpen) closeDropdown();
    else { createFloatingDropdown(); openDropdown(btn); }
  };

  window.setLanguage = async function (langCode) {
    await handleSetLanguage(langCode);
  };

  // ── Close on outside click / scroll / resize ──────────────────────
  document.addEventListener("click", (e) => {
    if (!dropdownOpen) return;
    const switcher = document.getElementById("langSwitcher");
    if (switcher && switcher.contains(e.target)) return;
    if (floatingDropdown && floatingDropdown.contains(e.target)) return;
    closeDropdown();
  });

  document.addEventListener("scroll", () => {
    if (dropdownOpen) {
      const btn = document.getElementById("langCurrentBtn");
      if (btn) positionDropdown(btn);
    }
  }, { passive: true });

  window.addEventListener("resize", () => {
    if (dropdownOpen) {
      const btn = document.getElementById("langCurrentBtn");
      if (btn) positionDropdown(btn);
      else closeDropdown();
    }
  });

  // ── Fetch shared header HTML ──────────────────────────────────────
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

  // ── Determine current page slug ───────────────────────────────────
  function getCurrentPage() {
    const path = window.location.pathname
      .replace(/\/$/, "")
      .replace(/\.html$/, "")
      .split("/")
      .filter(Boolean)
      .pop() || "home";
    return path;
  }

  // ── Mark active nav link ──────────────────────────────────────────
  function markActiveLink(container) {
    const page = getCurrentPage();
    container.querySelectorAll("[data-nav-page]").forEach((el) => {
      const isActive =
        el.getAttribute("data-nav-page") === page ||
        (page === "home" && el.getAttribute("data-nav-page") === "home");
      el.classList.toggle("active", isActive);
      if (isActive) {
        el.closest(".dropdown")
          ?.querySelector(".dropdown-toggle")
          ?.classList.add("active");
      }
    });
    if (
      window.location.pathname === "/" ||
      window.location.pathname === "/index.html"
    ) {
      container
        .querySelectorAll('[data-nav-page="home"]')
        .forEach((el) => el.classList.add("active"));
    }
  }

  // ── Wire mobile menu ──────────────────────────────────────────────
  function initMobileMenu(container) {
    const menuToggle = container.querySelector(".menu-toggle");
    const navLinks   = container.querySelector(".nav-links");
    const ddToggles  = container.querySelectorAll(".dropdown > a");
    if (!menuToggle || !navLinks) return;

    menuToggle.addEventListener("click", function () {
      navLinks.classList.toggle("active");
      this.setAttribute("aria-expanded",
        navLinks.classList.contains("active") ? "true" : "false");
    });

    container.querySelectorAll(".nav-links a:not(.dropdown > a)").forEach((link) => {
      link.addEventListener("click", () => {
        if (link.getAttribute("href")?.startsWith("#")) {
          navLinks.classList.remove("active");
          menuToggle.setAttribute("aria-expanded", "false");
        }
      });
    });

    ddToggles.forEach((toggle) => {
      toggle.addEventListener("click", function (e) {
        if (window.innerWidth <= 992) {
          e.preventDefault();
          const parent = this.parentElement;
          parent.classList.toggle("active");
          ddToggles.forEach((other) => {
            if (other.parentElement !== parent)
              other.parentElement.classList.remove("active");
          });
        }
      });
    });

    document.addEventListener("click", (e) => {
      if (window.innerWidth > 992) {
        container.querySelectorAll(".dropdown").forEach((dd) => {
          if (!dd.contains(e.target)) dd.classList.remove("active");
        });
      }
    });
  }

  // ── Wire header search ────────────────────────────────────────────
  function initHeaderSearch(container) {
    const sc    = container.querySelector(".header-search-container");
    const btn   = container.querySelector("#searchToggle");
    const input = container.querySelector("#headerSearch");
    if (!sc || !btn || !input) return;

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      sc.classList.toggle("active");
      if (sc.classList.contains("active")) setTimeout(() => input.focus(), 50);
    });

    input.addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      const term = input.value.trim();
      if (!term) return;
      if (typeof window.performKeywordSearch === "function") {
        window.performKeywordSearch(term);
      } else {
        window.location.href = `/?search=${encodeURIComponent(term)}`;
      }
    });

    document.addEventListener("click", (e) => {
      if (
        window.innerWidth > 768 &&
        !sc.contains(e.target) &&
        e.target !== btn &&
        e.target !== input
      ) {
        sc.classList.remove("active");
      }
    });
  }

  // ── Handle ?search= param on home page ───────────────────────────
  function handleSearchParam() {
    if (
      window.location.pathname !== "/" &&
      !window.location.pathname.endsWith("index.html")
    ) return;
    const term = new URLSearchParams(window.location.search).get("search");
    if (term && typeof window.performKeywordSearch === "function") {
      setTimeout(() => window.performKeywordSearch(term), 1000);
    }
  }

  // ── Main init ─────────────────────────────────────────────────────
  async function init() {
    const mountPoint = document.getElementById("site-header");
    if (!mountPoint) {
      console.warn("[header-loader] No #site-header element found.");
      return;
    }

    const headerHTML = await fetchHeader();
    if (!headerHTML) return;

    mountPoint.innerHTML = headerHTML;

    markActiveLink(mountPoint);
    initMobileMenu(mountPoint);
    initHeaderSearch(mountPoint);
    rebuildSwitcherButton();

    function applyI18n() {
      if (window.i18n) {
        window.i18n.applyStaticTranslations?.();
        rebuildSwitcherButton();
      }
    }

    if (window.i18n) {
      applyI18n();
    } else {
      let attempts = 0;
      const poll = setInterval(() => {
        attempts++;
        if (window.i18n) { applyI18n(); clearInterval(poll); }
        if (attempts > 30) clearInterval(poll);
      }, 100);
    }

    handleSearchParam();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
