/* main.js — UI interactions for Mswaki app (vanilla JS)
   - Sidebar toggle (mobile)
   - User menu
   - Theme (dark) toggle (persists to localStorage)
   - Toast notifications
   - Basic form validation helpers
   - Chart.js initialization scaffold (optional)
*/

(function () {
  "use strict";

  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => Array.from(ctx.querySelectorAll(sel));

  /* ---------- DOM references ---------- */
  const mobileToggle = $("#mobile-nav-toggle");
  const sidebar = $("#sidebar");
  const userBtn = $("#user-menu-btn");
  const userMenu = $("#user-menu");
  const themeToggle = $("#theme-toggle");
  const toastContainer = $("#toast-container");

  /* ---------- Utilities ---------- */
  function setAria(el, prop, value) {
    if (el) el.setAttribute(prop, value);
  }

  /* ---------- Mobile sidebar toggle ---------- */
  if (mobileToggle && sidebar) {
    mobileToggle.addEventListener("click", () => {
      const expanded = mobileToggle.getAttribute("aria-expanded") === "true";
      mobileToggle.setAttribute("aria-expanded", String(!expanded));
      sidebar.classList.toggle("open");
      // For accessibility: trap focus when open could be added here
    });
  }

  /* ---------- User menu ---------- */
  if (userBtn && userMenu) {
    userBtn.addEventListener("click", (e) => {
      const expanded = userBtn.getAttribute("aria-expanded") === "true";
      userBtn.setAttribute("aria-expanded", String(!expanded));
      userMenu.style.display = expanded ? "none" : "block";
      userMenu.setAttribute("aria-hidden", String(expanded));
    });

    // Close the menu when clicking outside
    document.addEventListener("click", (e) => {
      if (!userBtn.contains(e.target) && !userMenu.contains(e.target)) {
        userMenu.style.display = "none";
        userBtn.setAttribute("aria-expanded", "false");
        userMenu.setAttribute("aria-hidden", "true");
      }
    });
  }

  /* ---------- Theme toggle (dark mode) ---------- */
  (function themeInit() {
    const saved = localStorage.getItem("mswaki-theme");
    const root = document.documentElement;
    const body = document.body;
    if (saved) {
      body.setAttribute("data-theme", saved);
      if (themeToggle) themeToggle.setAttribute("aria-pressed", String(saved === "dark"));
    }
    if (themeToggle) {
      themeToggle.addEventListener("click", () => {
        const current = body.getAttribute("data-theme") === "dark" ? "dark" : "light";
        const next = current === "dark" ? "light" : "dark";
        body.setAttribute("data-theme", next);
        localStorage.setItem("mswaki-theme", next);
        themeToggle.setAttribute("aria-pressed", String(next === "dark"));
        showToast(`Switched to ${next} mode`);
      });
    }
  })();

  /* ---------- Toast notifications ---------- */
  function showToast(message = "", { timeout = 3500 } = {}) {
    if (!toastContainer) return;
    const el = document.createElement("div");
    el.className = "toast card";
    el.setAttribute("role", "status");
    el.textContent = message;
    toastContainer.appendChild(el);

    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(6px)";
      setTimeout(() => el.remove(), 250);
    }, timeout);
  }

  // Example: show a welcome toast if not shown before
  if (!localStorage.getItem("mswaki-welcome")) {
    showToast("Welcome to Mswaki dashboard — safe journeys!");
    localStorage.setItem("mswaki-welcome", "1");
  }

  /* ---------- Basic form helpers (client-side) ---------- */
  function validateForm(form) {
    const invalid = [];
    const inputs = $$(".required", form);
    inputs.forEach((fld) => {
      if (!fld.value || !fld.value.trim()) invalid.push(fld);
      fld.classList.toggle("invalid", !fld.value || !fld.value.trim());
    });
    if (invalid.length) {
      invalid[0].focus();
      showToast("Please fill required fields");
      return false;
    }
    return true;
  }

  // Attach simple client-side validation for forms with data-validate attribute
  $$("form[data-validate]").forEach((form) => {
    form.addEventListener("submit", (e) => {
      if (!validateForm(form)) e.preventDefault();
    });
  });

  /* ---------- Chart scaffold (Chart.js recommended) ----------
     To use, include Chart.js in your template:
     <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
     And call initRevenueChart() once data is available (or on DOMContentLoaded).
  */
  function initRevenueChart(canvasId = "revenueChart", labels = [], data = []) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;
    // If Chart is not available, show a small message
    if (typeof Chart === "undefined") {
      ctx.parentElement.innerHTML = "<p style='color:var(--muted)'>Chart.js not loaded — include it to show charts.</p>";
      return;
    }
    return new Chart(ctx.getContext("2d"), {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Revenue (KES)",
          data: data,
          borderWidth: 2,
          fill: true,
          tension: 0.3,
          backgroundColor: "rgba(99,102,241,0.08)",
          borderColor: getComputedStyle(document.body).getPropertyValue("--accent") || "#6366f1"
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { ticks: { color: getComputedStyle(document.body).getPropertyValue("--muted") } },
          y: { ticks: { color: getComputedStyle(document.body).getPropertyValue("--muted") } }
        },
        plugins: {
          legend: { display: false }
        }
      }
    });
  }

  // Try to initialize a dummy chart if canvas exists and server provides data via global variable
  document.addEventListener("DOMContentLoaded", () => {
    if (window.MSWAKI_CHART_DATA && window.MSWAKI_CHART_DATA.revenue) {
      const { labels, data } = window.MSWAKI_CHART_DATA.revenue;
      initRevenueChart("revenueChart", labels, data);
    } else {
      // if no data, still call init with placeholder to show guidance
      initRevenueChart("revenueChart", ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"], [1200,900,1400,1200,1600,1300,1700]);
    }
  });

  /* ---------- Export / CSV helper (basic) ---------- */
  function downloadCSV(filename = "export.csv", rows = []) {
    const csv = rows.map(r => r.map(c => `"${String(c).replace(/"/g,'""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  // hook example for an export button
  const exportBtn = document.getElementById("export-btn");
  if (exportBtn) {
    exportBtn.addEventListener("click", (e) => {
      // In production, fetch CSV from server or build rows dynamically
      const sample = [
        ["BookingID","User","Amount"],
        ["B-001","Alice","120"],
        ["B-002","Ben","100"]
      ];
      downloadCSV("bookings.csv", sample);
      showToast("Export started");
    });
  }

  /* ---------- Expose small API for other modules if needed ---------- */
  window.MswakiUI = {
    showToast,
    initRevenueChart,
    downloadCSV
  };

})();
