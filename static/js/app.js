// Quantity steppers: buttons with data-step adjust sibling input[type=number]
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-step]");
  if (!btn) return;
  const input = btn.parentElement.querySelector("input[type=number]");
  if (!input) return;
  const step = parseInt(btn.dataset.step, 10) || 1;
  const min = parseInt(input.min, 10) || 1;
  const max = parseInt(input.max, 10) || 99;
  const next = Math.min(max, Math.max(min, parseInt(input.value, 10) + step));
  input.value = next;
  input.dispatchEvent(new Event("change", { bubbles: true }));
});

// Theme toggle (dark mode)
document.addEventListener("click", (e) => {
  const btn = e.target.closest("#theme-toggle, [data-theme-toggle]");
  if (!btn) return;
  const dark = document.documentElement.classList.toggle("dark");
  localStorage.setItem("theme", dark ? "dark" : "light");
});

// Banner slider
(function () {
  const track = document.getElementById("banner-track");
  if (!track) return;
  const slides = track.querySelectorAll(".banner-slide");
  if (slides.length < 2) return;
  const dots = document.querySelectorAll(".banner-dot");
  let idx = 0;
  const count = slides.length;
  // RTL: moving forward translates positive X
  function go(i) {
    idx = (i + count) % count;
    track.style.transform = `translateX(${idx * 100}%)`;
    dots.forEach((d, n) => d.classList.toggle("bg-white", n === idx));
    dots.forEach((d, n) => d.classList.toggle("bg-white/60", n !== idx));
  }
  document.getElementById("banner-next")?.addEventListener("click", () => { go(idx + 1); restart(); });
  document.getElementById("banner-prev")?.addEventListener("click", () => { go(idx - 1); restart(); });
  dots.forEach((d) => d.addEventListener("click", () => { go(parseInt(d.dataset.index, 10)); restart(); }));
  let timer = setInterval(() => go(idx + 1), 5000);
  function restart() { clearInterval(timer); timer = setInterval(() => go(idx + 1), 5000); }
  go(0);
})();

// Live search: dismiss dropdown on outside click / Escape / empty input
(function () {
  document.addEventListener("click", (e) => {
    const box = document.getElementById("live-search-results");
    if (box && !e.target.closest("#live-search-wrap")) box.remove();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") document.getElementById("live-search-results")?.remove();
  });
  document.addEventListener("input", (e) => {
    if (e.target.matches('#live-search-wrap input[name="q"]') && e.target.value.trim().length < 2) {
      document.getElementById("live-search-results")?.remove();
    }
  });
})();

// HTMX error responses (e.g. 429 rate limit) are not swapped — show a short toast instead
document.body.addEventListener("htmx:responseError", (e) => {
  const xhr = e.detail.xhr;
  const message = xhr.status === 429 && xhr.responseText
    ? xhr.responseText
    : "خطایی رخ داد. لطفاً دوباره تلاش کنید.";
  const toast = document.createElement("div");
  toast.setAttribute("role", "alert");
  toast.className = "fixed bottom-5 inset-x-4 sm:inset-x-auto sm:left-5 z-50 max-w-sm rounded-xl bg-gray-900 dark:bg-ember text-white text-sm leading-6 px-4 py-3 shadow-lg";
  toast.textContent = message;
  document.body.appendChild(toast);
  setTimeout(() => toast.remove(), 6000);
});

// SMS code resend: count down data-wait seconds, then enable the button
(function () {
  const btn = document.getElementById("otp-resend");
  const label = document.getElementById("otp-countdown");
  if (!btn || !label) return;
  const faDigits = (n) => String(n).replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
  let left = parseInt(btn.dataset.wait, 10) || 0;
  (function tick() {
    if (left <= 0) {
      btn.disabled = false;
      label.textContent = "";
      return;
    }
    label.textContent = ` (${faDigits(left)} ثانیه)`;
    left -= 1;
    setTimeout(tick, 1000);
  })();
})();

// Global HTMX config
document.body.addEventListener("htmx:configRequest", (e) => {
  e.detail.headers["X-CSRFToken"] = document.body.getAttribute("data-csrf") ||
    (document.body.getAttribute("hx-headers") &&
      JSON.parse(document.body.getAttribute("hx-headers"))["X-CSRFToken"]) || "";
});

// Variant picker (product page): price, stock, photo and the add button follow the chosen colour/option
document.addEventListener("change", (e) => {
  const input = e.target.closest("[data-variant-picker] input[name=variant]");
  if (!input) return;
  const d = input.dataset;
  const each = (selector, fn) => document.querySelectorAll(selector).forEach(fn);
  const stock = parseInt(d.vStock, 10) || 0;
  each("[data-variant-label]", (el) => (el.textContent = d.vLabel));
  each("[data-price]", (el) => (el.textContent = d.vPrice));
  each("[data-old-price]", (el) => (el.textContent = d.vOldPrice));
  each("[data-discount]", (el) => (el.textContent = d.vDiscount));
  each("[data-old-price-row], [data-discount-badge]", (el) => (el.hidden = !d.vDiscount));
  each("[data-in-stock]", (el) => (el.hidden = stock === 0));
  each("[data-out-of-stock]", (el) => (el.hidden = stock > 0));
  each("[data-stock-count]", (el) => (el.textContent = d.vStockText));
  each("[data-add-button]", (el) => (el.disabled = stock === 0));
  each("[data-add-label]", (el) => (el.textContent = stock ? "افزودن به سبد خرید" : "این مدل ناموجود است"));
  each("#qty-input", (el) => {
    el.max = Math.max(stock, 1);
    if (parseInt(el.value, 10) > stock) el.value = Math.max(stock, 1);
  });
  if (d.vImage) each("[data-main-image]", (el) => (el.src = d.vImage));
  const url = new URL(window.location.href);
  url.searchParams.set("v", input.value);
  history.replaceState(null, "", url);
});
