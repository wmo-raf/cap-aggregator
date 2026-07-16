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
  // Homepage alert-list filtering lives in home.ts (it shares state with the
  // homepage map's severity/time controls).
});
