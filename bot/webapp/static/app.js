(() => {
  "use strict";

  const tg = window.Telegram ? window.Telegram.WebApp : null;
  const STORAGE_KEY = "shop_cart_v1";

  const state = {
    shop: null,
    categories: [],
    products: [],
    cart: {},
    category: "all",
    search: "",
    submitting: false,
    openSheet: null,
  };

  const $ = (id) => document.getElementById(id);

  const fmt = (value) =>
    new Intl.NumberFormat("ru-RU").format(Math.round(value || 0)) +
    " " +
    (state.shop && state.shop.currency ? state.shop.currency : "so'm");

  // --- telegram bootstrap -------------------------------------------------
  function initTelegram() {
    if (!tg) return;
    try {
      tg.ready();
      tg.expand();
      tg.setHeaderColor("secondary_bg_color");
      tg.setBackgroundColor("bg_color");
      tg.disableVerticalSwipes && tg.disableVerticalSwipes();
    } catch (_) {
      /* older clients */
    }
    if (tg.BackButton) {
      tg.BackButton.onClick(() => {
        if (state.openSheet) closeSheet(state.openSheet);
        else if (tg) tg.close();
      });
    }
    if (!tg.initData) {
      showBanner(
        "Mini App Telegram tashqarisida ochilgan. Buyurtma berish uchun uni bot menyusidan oching."
      );
    }
  }

  function haptic(type) {
    try {
      if (!tg || !tg.HapticFeedback) return;
      if (type === "success") tg.HapticFeedback.notificationOccurred("success");
      else if (type === "error") tg.HapticFeedback.notificationOccurred("error");
      else tg.HapticFeedback.impactOccurred("light");
    } catch (_) {}
  }

  function showBanner(text) {
    const el = $("banner");
    el.textContent = text;
    el.hidden = false;
  }

  // --- cart persistence ---------------------------------------------------
  function loadCart() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
      state.cart = {};
      Object.entries(raw).forEach(([id, qty]) => {
        const productId = Number(id);
        const quantity = Number(qty);
        if (Number.isInteger(productId) && Number.isInteger(quantity) && quantity > 0) {
          state.cart[productId] = quantity;
        }
      });
    } catch (_) {
      state.cart = {};
    }
  }

  function saveCart() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.cart));
    } catch (_) {}
  }

  function cartLines() {
    return Object.entries(state.cart)
      .map(([id, qty]) => {
        const product = state.products.find((item) => item.id === Number(id));
        return product ? { product, qty } : null;
      })
      .filter(Boolean);
  }

  function totals() {
    const lines = cartLines();
    const subtotal = lines.reduce((sum, line) => sum + line.product.price * line.qty, 0);
    const shop = state.shop || {};
    let delivery = 0;
    if (subtotal > 0 && shop.delivery_fee > 0) {
      const freeFrom = Number(shop.free_delivery_from || 0);
      delivery = freeFrom > 0 && subtotal >= freeFrom ? 0 : Number(shop.delivery_fee);
    }
    const count = lines.reduce((sum, line) => sum + line.qty, 0);
    return { lines, subtotal, delivery, total: subtotal + delivery, count };
  }

  function addToCart(productId, delta) {
    const product = state.products.find((item) => item.id === productId);
    if (!product || product.stock <= 0) return;
    const current = state.cart[productId] || 0;
    const next = Math.max(0, Math.min(product.stock, current + delta));
    if (next === 0) delete state.cart[productId];
    else state.cart[productId] = next;
    saveCart();
    haptic("light");
    renderAll();
    if (state.openSheet === "cart") renderCartSheet();
  }

  // --- rendering ----------------------------------------------------------
  function renderAll() {
    renderBadge();
    renderProducts();
    renderCartSheet();
  }

  function renderBadge() {
    const count = totals().count;
    const badge = $("cart-badge");
    badge.textContent = String(count);
    badge.hidden = count === 0;
  }

  function renderCategories() {
    const nav = $("categories");
    nav.textContent = "";
    const chips = [{ id: "all", label: "✨ Barchasi" }].concat(
      state.categories.map((category) => ({
        id: category.id,
        label: `${category.emoji} ${category.title}`,
      }))
    );
    chips.forEach((chip) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "chip" + (state.category === chip.id ? " active" : "");
      button.textContent = chip.label;
      button.addEventListener("click", () => {
        state.category = chip.id;
        renderCategories();
        renderProducts();
        haptic("light");
      });
      nav.appendChild(button);
    });
  }

  function visibleProducts() {
    const query = state.search.trim().toLowerCase();
    return state.products.filter((product) => {
      if (state.category !== "all" && product.category_id !== state.category) return false;
      if (!query) return true;
      const haystack = (product.title + " " + (product.description || "")).toLowerCase();
      return haystack.includes(query);
    });
  }

  function productCard(product) {
    const card = document.createElement("article");
    card.className = "card";

    const media = document.createElement("div");
    media.className = "card-media";
    if (product.photo) {
      const img = document.createElement("img");
      img.loading = "lazy";
      img.src = product.photo;
      img.alt = product.title;
      img.addEventListener("error", () => {
        media.textContent = "";
        const placeholder = document.createElement("span");
        placeholder.className = "placeholder";
        placeholder.textContent = "🛍";
        media.appendChild(placeholder);
      });
      media.appendChild(img);
    } else {
      const placeholder = document.createElement("span");
      placeholder.className = "placeholder";
      placeholder.textContent = "🛍";
      media.appendChild(placeholder);
    }

    const body = document.createElement("div");
    body.className = "card-body";

    const title = document.createElement("h2");
    title.className = "card-title";
    title.textContent = product.title;

    const priceRow = document.createElement("div");
    priceRow.className = "price-row";
    const price = document.createElement("span");
    price.className = "price";
    price.textContent = fmt(product.price);
    priceRow.appendChild(price);
    if (product.old_price && product.old_price > product.price) {
      const old = document.createElement("span");
      old.className = "old-price";
      old.textContent = fmt(product.old_price);
      priceRow.appendChild(old);
    }

    const stock = document.createElement("div");
    stock.className = "stock" + (product.stock <= 0 ? " out" : "");
    stock.textContent =
      product.stock > 0 ? `📦 ${product.stock} dona` : "⛔️ Omborda qolmagan";

    const addRow = document.createElement("div");
    addRow.className = "add-row";
    const inCart = state.cart[product.id] || 0;

    if (product.stock <= 0) {
      const button = document.createElement("button");
      button.className = "btn";
      button.type = "button";
      button.disabled = true;
      button.textContent = "Tugagan";
      addRow.appendChild(button);
    } else if (inCart > 0) {
      const stepper = document.createElement("div");
      stepper.className = "stepper";
      const minus = document.createElement("button");
      minus.type = "button";
      minus.textContent = "−";
      minus.addEventListener("click", () => addToCart(product.id, -1));
      const count = document.createElement("span");
      count.textContent = `${inCart} ta`;
      const plus = document.createElement("button");
      plus.type = "button";
      plus.textContent = "+";
      plus.addEventListener("click", () => addToCart(product.id, 1));
      stepper.append(minus, count, plus);
      addRow.appendChild(stepper);
    } else {
      const button = document.createElement("button");
      button.className = "btn primary";
      button.type = "button";
      button.textContent = "🛒 Savatga";
      button.addEventListener("click", () => addToCart(product.id, 1));
      addRow.appendChild(button);
    }

    body.append(title, priceRow, stock, addRow);
    card.append(media, body);
    return card;
  }

  function renderProducts() {
    const grid = $("products");
    grid.textContent = "";
    const products = visibleProducts();
    $("empty").hidden = products.length > 0;
    products.forEach((product) => grid.appendChild(productCard(product)));
  }

  function renderCartSheet() {
    const { lines, subtotal, delivery, total } = totals();
    const container = $("cart-items");
    container.textContent = "";

    if (!lines.length) {
      const empty = document.createElement("p");
      empty.className = "empty";
      empty.textContent = "Savat bo'sh. Katalogdan mahsulot tanlang.";
      container.appendChild(empty);
    }

    lines.forEach((line) => {
      const row = document.createElement("div");
      row.className = "cart-item";

      if (line.product.photo) {
        const img = document.createElement("img");
        img.src = line.product.photo;
        img.alt = line.product.title;
        row.appendChild(img);
      } else {
        const thumb = document.createElement("div");
        thumb.className = "thumb";
        thumb.textContent = "🛍";
        row.appendChild(thumb);
      }

      const info = document.createElement("div");
      const title = document.createElement("div");
      title.className = "cart-item-title";
      title.textContent = line.product.title;
      const price = document.createElement("div");
      price.className = "cart-item-price";
      price.textContent = `${fmt(line.product.price)} × ${line.qty} = ${fmt(
        line.product.price * line.qty
      )}`;
      info.append(title, price);

      const controls = document.createElement("div");
      controls.className = "qty-controls";
      const minus = document.createElement("button");
      minus.type = "button";
      minus.textContent = "−";
      minus.addEventListener("click", () => addToCart(line.product.id, -1));
      const count = document.createElement("span");
      count.textContent = String(line.qty);
      const plus = document.createElement("button");
      plus.type = "button";
      plus.textContent = "+";
      plus.addEventListener("click", () => addToCart(line.product.id, 1));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove-btn";
      remove.textContent = "🗑";
      remove.addEventListener("click", () => {
        delete state.cart[line.product.id];
        saveCart();
        renderAll();
        renderCartSheet();
      });
      controls.append(minus, count, plus, remove);

      row.append(info, controls);
      container.appendChild(row);
    });

    const summary = $("cart-summary");
    summary.textContent = "";
    summary.append(
      summaryRow("Mahsulotlar", fmt(subtotal)),
      summaryRow("Yetkazish", delivery === 0 ? "bepul 🎁" : fmt(delivery)),
      summaryRow("Jami", fmt(total), "total")
    );

    $("checkout-button").disabled = lines.length === 0;
    $("send-to-bot").disabled = lines.length === 0;
  }

  function summaryRow(label, value, className) {
    const row = document.createElement("div");
    row.className = "row" + (className ? " " + className : "");
    const left = document.createElement("span");
    left.textContent = label;
    const right = document.createElement("span");
    right.textContent = value;
    row.append(left, right);
    return row;
  }

  // --- sheets -------------------------------------------------------------
  function openSheet(name) {
    state.openSheet = name;
    const panel = $(name + "-panel");
    if (!panel) return;
    panel.hidden = false;
    document.body.style.overflow = "hidden";
    try {
      tg && tg.BackButton && tg.BackButton.show();
    } catch (_) {}
  }

  function closeSheet(name) {
    const panel = $(name + "-panel");
    if (panel) panel.hidden = true;
    if (state.openSheet === name) state.openSheet = null;
    if (!state.openSheet) {
      document.body.style.overflow = "";
      try {
        tg && tg.BackButton && tg.BackButton.hide();
      } catch (_) {}
    }
  }

  function renderCheckout() {
    const { subtotal, delivery, total, count } = totals();
    const summary = $("checkout-summary");
    summary.textContent = "";
    summary.append(
      summaryRow(`Mahsulotlar (${count} dona)`, fmt(subtotal)),
      summaryRow("Yetkazish", delivery === 0 ? "bepul 🎁" : fmt(delivery)),
      summaryRow("Jami", fmt(total), "total")
    );

    const shop = state.shop || {};
    const starsInput = document.querySelector('input[name="payment"][value="stars"]');
    const cardInput = document.querySelector('input[name="payment"][value="card"]');
    if (starsInput) {
      const wrapper = starsInput.closest("label");
      const available = Number(shop.stars_rate || 0) > 0;
      if (wrapper) wrapper.hidden = !available;
      if (!available && starsInput.checked) {
        document.querySelector('input[name="payment"][value="cash"]').checked = true;
      }
    }
    if (cardInput) {
      const wrapper = cardInput.closest("label");
      if (wrapper) wrapper.hidden = !shop.card_available;
      if (!shop.card_available && cardInput.checked) {
        document.querySelector('input[name="payment"][value="cash"]').checked = true;
      }
    }
  }

  function showFormError(message) {
    const el = $("form-error");
    el.textContent = message;
    el.hidden = !message;
  }

  function setSubmitting(value) {
    state.submitting = value;
    const button = $("submit-order");
    button.disabled = value;
    button.textContent = value ? "⏳ Yuborilmoqda…" : "Buyurtmani tasdiqlash";
  }

  function showSuccess(data) {
    $("success-title").textContent =
      data.payment === "stars" ? "Buyurtma yaratildi ⭐️" : "Buyurtma qabul qilindi! 🎉";
    let text = `Buyurtma raqami: #${data.code}\nJami: ${fmt(data.total)}`;
    if (data.payment === "stars") {
      text += "\n\nTo'lov oynasida Telegram Stars orqali to'lovni yakunlang.";
    } else if (data.payment === "card") {
      text += "\n\nKarta rekvizitlari bot orqali yuborildi. To'lov chekini botga yuboring.";
    } else {
      text += "\n\nOperator buyurtmani tasdiqlash uchun tez orada bog'lanadi.";
    }
    $("success-text").textContent = text;
    openSheet("success");
    haptic("success");
  }

  // --- data ---------------------------------------------------------------
  async function loadCatalog() {
    try {
      const response = await fetch("/api/catalog", { headers: { Accept: "application/json" } });
      if (!response.ok) throw new Error("catalog");
      const data = await response.json();
      state.shop = data.shop;
      state.categories = data.categories || [];
      state.products = data.products || [];

      const known = new Set(state.products.map((product) => product.id));
      Object.keys(state.cart).forEach((id) => {
        if (!known.has(Number(id))) delete state.cart[id];
      });
      saveCart();

      $("shop-name").textContent = data.shop.name || "Do'kon";
      document.title = data.shop.name || "Do'kon";
      $("shop-sub").textContent = data.shop.support
        ? "☎️ @" + String(data.shop.support).replace(/^@/, "")
        : "Tez va oson xarid";
      $("shop-hours").textContent = "Xaridingiz uchun rahmat! 💙";

      renderCategories();
      renderProducts();
      renderCartSheet();
      renderBadge();
    } catch (_) {
      showBanner("Do'kon ma'lumotlarini yuklab bo'lmadi. Sahifani yangilang.");
    }
  }

  async function submitOrder(event) {
    event.preventDefault();
    if (state.submitting) return;
    showFormError("");

    const items = cartLines().map((line) => ({ id: line.product.id, qty: line.qty }));
    if (!items.length) {
      showFormError("Savat bo'sh.");
      return;
    }
    if (!tg || !tg.initData) {
      showFormError("Buyurtma berish uchun Mini App'ni Telegram orqali oching.");
      return;
    }

    const form = $("checkout-form");
    const formData = new FormData(form);
    const payload = {
      initData: tg.initData,
      items,
      name: String(formData.get("name") || "").trim(),
      phone: String(formData.get("phone") || "").trim(),
      address: String(formData.get("address") || "").trim(),
      comment: String(formData.get("comment") || "").trim(),
      promo: String(formData.get("promo") || "").trim(),
      payment: String(formData.get("payment") || "cash"),
    };

    if (payload.name.length < 2) return showFormError("Ismingizni kiriting.");
    if (payload.phone.replace(/\D/g, "").length < 9) return showFormError("Telefon raqam noto'g'ri.");
    if (payload.address.length < 5) return showFormError("Manzilni to'liq kiriting.");

    setSubmitting(true);
    try {
      const response = await fetch("/api/order", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({ ok: false, error: "Server xatosi." }));
      if (!response.ok || !data.ok) throw new Error(data.error || "Buyurtma yaratilmadi.");

      state.cart = {};
      saveCart();
      renderAll();
      form.reset();
      closeSheet("checkout");
      closeSheet("cart");
      showSuccess(data);

      if (data.payment === "stars" && data.invoice_link && tg.openInvoice) {
        tg.openInvoice(data.invoice_link, (status) => {
          const text = $("success-text");
          if (status === "paid") {
            text.textContent = `Buyurtma #${data.code} to'landi ✅\n\nRahmat! Operator tez orada bog'lanadi.`;
            haptic("success");
          } else if (status === "failed") {
            text.textContent = `Buyurtma #${data.code}\n\n⚠️ To'lov amalga oshmadi. "Buyurtmalarim" bo'limidan qayta to'lashingiz mumkin.`;
            haptic("error");
          } else {
            text.textContent = `Buyurtma #${data.code}\n\nTo'lovni yakunlamadingiz. Bot orqali qayta urinishingiz mumkin.`;
          }
        });
      }
    } catch (error) {
      showFormError(error.message || "Xatolik yuz berdi.");
      haptic("error");
    } finally {
      setSubmitting(false);
    }
  }

  function sendCartToBot() {
    const items = cartLines().map((line) => ({ id: line.product.id, qty: line.qty }));
    if (!items.length) return;
    if (!tg || typeof tg.sendData !== "function") {
      showBanner("Bu funksiya faqat Telegram ichida ishlaydi.");
      return;
    }
    try {
      tg.sendData(JSON.stringify({ action: "add", items }));
      tg.close();
    } catch (_) {
      showBanner("Savatni botga yuborib bo'lmadi. Bot menyusidan ochib ko'ring.");
    }
  }

  // --- wiring -------------------------------------------------------------
  function bind() {
    $("cart-button").addEventListener("click", () => {
      renderCartSheet();
      openSheet("cart");
    });
    $("checkout-button").addEventListener("click", () => {
      if (!cartLines().length) return;
      closeSheet("cart");
      renderCheckout();
      openSheet("checkout");
    });
    $("send-to-bot").addEventListener("click", sendCartToBot);
    $("checkout-form").addEventListener("submit", submitOrder);
    $("success-close").addEventListener("click", () => {
      if (tg) tg.close();
    });
    $("success-orders").addEventListener("click", () => {
      if (tg) tg.close();
    });

    $("search").addEventListener("input", (event) => {
      state.search = event.target.value || "";
      renderProducts();
    });

    document.addEventListener("click", (event) => {
      const closer = event.target.closest("[data-close]");
      if (closer) closeSheet(closer.dataset.close);
    });

    document.querySelectorAll('input[name="payment"]').forEach((input) => {
      input.addEventListener("change", () => {
        $("card-info").hidden = input.value !== "card" || !input.checked;
      });
    });
  }

  function start() {
    initTelegram();
    loadCart();
    bind();
    loadCatalog();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
