import "@/assets/main.css";

// Server-rendered public pages (base.html): design tokens + the header theme
// toggle. The theme itself is applied pre-paint by includes/theme_boot.html.
const STORAGE_KEY = "capagg-theme";

function syncLabels() {
  const dark = document.documentElement.classList.contains("dark");
  document.querySelectorAll("[data-theme-label]").forEach((el) => {
    el.textContent = dark ? "Light" : "Dark";
  });
}

document.addEventListener("DOMContentLoaded", () => {
  syncLabels();
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const dark = document.documentElement.classList.toggle("dark");
      localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
      syncLabels();
    });
  });

  // Homepage alert groups: all alerts are in the HTML; "View N more" toggles
  // the ones beyond the first two per authority.
  document.querySelectorAll<HTMLButtonElement>("[data-expand-alerts]").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.closest("[data-alert-group]");
      if (!group) return;
      const expand = button.getAttribute("aria-expanded") !== "true";
      group.querySelectorAll(".alert-extra").forEach((item) => item.classList.toggle("hidden", !expand));
      button.setAttribute("aria-expanded", String(expand));
      button.textContent = expand ? "Show less" : (button.dataset.moreLabel ?? "View more");
    });
  });
});
