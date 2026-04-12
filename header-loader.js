/**
 * PwaniStays — header-loader.js
 * ================================
 * Fetches /header.html, injects it into <div id="site-header">,
 * marks the active nav link, wires mobile menu, header search,
 * and calls buildSwitcher() (from i18n.js) to show the language toggle.
 *
 * HOW TO USE ON ANY PAGE
 * ──────────────────────
 * 1. In <head>:  <script src="/i18n.js"></script>
 * 2. In <head>:  <link rel="stylesheet" href="/header.css">
 * 3. In <body> top: <div id="site-header"></div>
 * 4. Before </body>: <script src="/header-loader.js"></script>
 */

(function() {

  // ── Fetch and inject header.html ───────────────────────────────
  function loadHeader() {
    var mount = document.getElementById("site-header");
    if (!mount) return;

    fetch("/header.html", { cache: "no-cache" })
      .then(function(res) { return res.ok ? res.text() : Promise.reject(res.status); })
      .then(function(html) {
        mount.innerHTML = html;
        onHeaderReady(mount);
      })
      .catch(function(err) {
        console.warn("[header-loader] Could not load header.html:", err);
      });
  }

  // ── Called once header HTML is in the DOM ──────────────────────
  function onHeaderReady(mount) {
    markActiveLink(mount);
    initMobileMenu(mount);
    initSearch(mount);
    applyTranslations();
  }

  // ── Mark the current page's nav link as active ─────────────────
  function markActiveLink(mount) {
    var slug = window.location.pathname
      .replace(/\/$/, "").replace(/\.html$/, "")
      .split("/").filter(Boolean).pop() || "home";

    mount.querySelectorAll("[data-nav-page]").forEach(function(el) {
      var match = el.getAttribute("data-nav-page") === slug ||
        (slug === "home" && el.getAttribute("data-nav-page") === "home");
      el.classList.toggle("active", match);
      if (match) {
        var dd = el.closest(".dropdown");
        if (dd) dd.querySelector(".dropdown-toggle").classList.add("active");
      }
    });
    if (window.location.pathname === "/" || window.location.pathname === "/index.html") {
      mount.querySelectorAll('[data-nav-page="home"]').forEach(function(el) {
        el.classList.add("active");
      });
    }
  }

  // ── Mobile menu ────────────────────────────────────────────────
  function initMobileMenu(mount) {
    var toggle   = mount.querySelector(".menu-toggle");
    var navLinks = mount.querySelector(".nav-links");
    var ddLinks  = mount.querySelectorAll(".dropdown > a");
    if (!toggle || !navLinks) return;

    toggle.addEventListener("click", function() {
      navLinks.classList.toggle("active");
      this.setAttribute("aria-expanded", navLinks.classList.contains("active"));
    });

    mount.querySelectorAll(".nav-links a:not(.dropdown > a)").forEach(function(a) {
      a.addEventListener("click", function() {
        if ((a.getAttribute("href") || "").startsWith("#")) {
          navLinks.classList.remove("active");
          toggle.setAttribute("aria-expanded", "false");
        }
      });
    });

    ddLinks.forEach(function(a) {
      a.addEventListener("click", function(e) {
        if (window.innerWidth <= 992) {
          e.preventDefault();
          var p = this.parentElement;
          p.classList.toggle("active");
          ddLinks.forEach(function(other) {
            if (other.parentElement !== p) other.parentElement.classList.remove("active");
          });
        }
      });
    });

    document.addEventListener("click", function(e) {
      if (window.innerWidth > 992) {
        mount.querySelectorAll(".dropdown").forEach(function(dd) {
          if (!dd.contains(e.target)) dd.classList.remove("active");
        });
      }
    });
  }

  // ── Header search ──────────────────────────────────────────────
  function initSearch(mount) {
    var sc    = mount.querySelector(".header-search-container");
    var btn   = mount.querySelector("#searchToggle");
    var input = mount.querySelector("#headerSearch");
    if (!sc || !btn || !input) return;

    btn.addEventListener("click", function(e) {
      e.preventDefault(); e.stopPropagation();
      sc.classList.toggle("active");
      if (sc.classList.contains("active")) setTimeout(function() { input.focus(); }, 50);
    });

    input.addEventListener("keydown", function(e) {
      if (e.key !== "Enter") return;
      e.preventDefault();
      var term = input.value.trim();
      if (!term) return;
      if (typeof window.performKeywordSearch === "function") {
        window.performKeywordSearch(term);
      } else {
        window.location.href = "/?search=" + encodeURIComponent(term);
      }
    });

    document.addEventListener("click", function(e) {
      if (window.innerWidth > 768 && !sc.contains(e.target) && e.target !== btn && e.target !== input) {
        sc.classList.remove("active");
      }
    });
  }

  // ── Apply i18n to newly-injected header + build switcher ───────
  function applyTranslations() {
    // applyStaticTranslations handles [data-i18n] elements in the header
    if (window.i18n && window.i18n.applyStaticTranslations) {
      window.i18n.applyStaticTranslations();
    }
    // buildSwitcher populates #langSwitcher (now in the DOM after header inject)
    if (typeof buildSwitcher === "function") {
      buildSwitcher();
    }
  }

  // ── Handle ?search= param when redirected from other pages ─────
  function handleSearchParam() {
    if (window.location.pathname !== "/" && !window.location.pathname.endsWith("index.html")) return;
    var term = new URLSearchParams(window.location.search).get("search");
    if (term && typeof window.performKeywordSearch === "function") {
      setTimeout(function() { window.performKeywordSearch(term); }, 1000);
    }
  }

  // ── Run ────────────────────────────────────────────────────────
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function() {
      loadHeader();
      handleSearchParam();
    });
  } else {
    loadHeader();
    handleSearchParam();
  }

})();
