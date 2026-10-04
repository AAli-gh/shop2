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
  // results are appended to the form: drop the previous dropdown so only the newest shows
  document.body.addEventListener("htmx:beforeSwap", (e) => {
    if (e.detail.target && e.detail.target.id === "live-search-wrap") {
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

// Countdown chips (flash sale): <span data-countdown="2026-09-30T20:00:00+03:30">
(function () {
  const boxes = () => document.querySelectorAll("[data-countdown]");
  const fa = (n) => String(n).padStart(2, "0").replace(/\d/g, (d) => "۰۱۲۳۴۵۶۷۸۹"[d]);
  function tick() {
    boxes().forEach((el) => {
      const end = new Date(el.dataset.countdown).getTime();
      if (isNaN(end)) return;
      let left = Math.floor((end - Date.now()) / 1000);
      if (left <= 0) { el.textContent = "پایان یافت"; return; }
      const days = Math.floor(left / 86400);
      left -= days * 86400;
      const clock = `${fa(Math.floor(left / 3600))}:${fa(Math.floor((left % 3600) / 60))}:${fa(left % 60)}`;
      el.textContent = days ? `${fa(days)} روز و ${clock}` : clock;
    });
  }
  tick();
  setInterval(tick, 1000);
})();

// Product gallery: thumbnails swap the main photo, clicking it opens a zoomable overlay
(function () {
  let overlay = null;
  function close() {
    overlay?.remove();
    overlay = null;
    document.body.style.overflow = "";
  }
  function open(src, alt) {
    close();
    overlay = document.createElement("div");
    overlay.dataset.lightbox = "";
    overlay.className = "fixed inset-0 z-[100] flex items-center justify-center bg-black/80 p-4";
    // src and alt come from the page (the alt is the product name), so set them as properties, never as HTML
    const img = document.createElement("img");
    img.src = src;
    img.alt = alt || "";
    img.className = "max-h-full max-w-full cursor-zoom-in rounded-xl transition-transform duration-200";
    overlay.innerHTML = `<button type="button" data-lightbox-close aria-label="بستن" class="absolute top-4 left-4 flex h-11 w-11 items-center justify-center rounded-xl bg-white/15 text-2xl text-white">×</button>`;
    overlay.prepend(img);
    document.body.appendChild(overlay);
    document.body.style.overflow = "hidden";
  }
  document.addEventListener("click", (e) => {
    const thumb = e.target.closest("[data-gallery-thumb]");
    if (thumb) {
      const main = document.querySelector("[data-main-image]");
      if (main) {
        main.src = thumb.dataset.preview || thumb.dataset.full;
        main.dataset.full = thumb.dataset.full;
      }
      return;
    }
    const main = e.target.closest("[data-main-image]");
    if (main) { open(main.dataset.full || main.src, main.alt); return; }
    if (!overlay) return;
    const picture = e.target.closest("[data-lightbox] img");
    if (picture && !e.target.closest("[data-lightbox-close]")) {
      const zoomed = picture.style.transform !== "";
      picture.style.transform = zoomed ? "" : "scale(2)";
      picture.className = picture.className.replace(zoomed ? "cursor-zoom-out" : "cursor-zoom-in",
                                                    zoomed ? "cursor-zoom-in" : "cursor-zoom-out");
      return;
    }
    close();
  });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
})();

// Copy buttons: data-copy="#id" copies that element's text; with data-share-title it opens the phone's share sheet when there is one
document.addEventListener("click", async (e) => {
  const button = e.target.closest("[data-copy]");
  if (!button) return;
  const text = document.querySelector(button.dataset.copy)?.textContent.trim();
  if (!text) return;
  if (button.dataset.shareTitle && navigator.share) {
    try { await navigator.share({ title: button.dataset.shareTitle, url: text }); return; } catch (err) { if (err.name === "AbortError") return; }
  }
  try {
    await navigator.clipboard.writeText(text);
    const label = button.textContent;
    button.textContent = "کپی شد ✓";
    setTimeout(() => { button.textContent = label; }, 1500);
  } catch (err) {
    window.prompt("کپی کنید:", text);
  }
});

// «جستجوی مجدد» on an empty result: back to the header search box
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-focus-search]")) return;
  const box = document.querySelector('#live-search-wrap input[name="q"]');
  if (box) { window.scrollTo({ top: 0, behavior: "smooth" }); box.select(); box.focus(); }
});

// offline fallback page (templates/sw.js); skipped where service workers aren't available
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
}
