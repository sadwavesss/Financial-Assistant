// Transaction form: live exchange rate lookup, BYN preview and category filtering by type.
(() => {
    const form = document.getElementById("transaction-form");
    const { currency, date, amount, category_id: category } = form.elements;
    const manualRate = document.getElementById("manual_rate");
    const autoRadio = document.getElementById("rate_mode_auto");
    const rateBlock = document.getElementById("rate-block");
    const rateInfo = document.getElementById("rate-info");
    const historyOption = document.getElementById("history-option");
    const historyLabel = document.getElementById("history-label");
    const preview = document.getElementById("byn-preview");

    let autoRate = null;
    let historyRate = Number(form.dataset.historyRate) || null;

    const parseNumber = (text) => Number(String(text).replace(/\s/g, "").replace(",", "."));
    const formatRate = (value) => Number(value).toLocaleString("ru-RU", { maximumFractionDigits: 6 });
    const formatMoney = (value) =>
        value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const formatDate = (iso) => iso.split("-").reverse().join(".");
    const selectedMode = () => form.querySelector("input[name=rate_mode]:checked")?.value;
    const setMode = (mode) => { form.querySelector(`input[name=rate_mode][value=${mode}]`).checked = true; };

    function showInfo(text, style) {
        rateInfo.textContent = text;
        rateInfo.className = `small mb-2 ${style}`;
    }

    function showUnavailable(detail) {
        autoRate = null;
        autoRadio.disabled = true;
        showInfo(detail.message, "text-danger");
        if (detail.history) {
            historyRate = Number(detail.history.rate);
            historyLabel.textContent = `${formatRate(historyRate)} BYN (${formatDate(detail.history.date)})`;
            historyOption.classList.remove("d-none");
            setMode("history");
        } else {
            historyRate = null;
            historyOption.classList.add("d-none");
            setMode("manual");
        }
    }

    async function refreshRate() {
        const foreign = currency.value !== "BYN";
        rateBlock.classList.toggle("d-none", !foreign);
        if (!foreign || !date.value) {
            updatePreview();
            return;
        }
        showInfo("Получаем курс…", "text-body-secondary");
        try {
            const response = await fetch(`/api/rates/${currency.value}?date=${date.value}`);
            const body = await response.json();
            if (!response.ok) {
                showUnavailable(body.detail);
            } else {
                autoRate = Number(body.rate);
                autoRadio.disabled = false;
                historyOption.classList.add("d-none");
                showInfo(
                    `Курс ${body.source_label} на ${formatDate(body.date)}: ` +
                    `${formatRate(autoRate)} BYN за 1 ${currency.value}`,
                    "text-success",
                );
                if (selectedMode() !== "manual") setMode("auto");
            }
        } catch {
            showUnavailable({ message: "Не удалось связаться с сервером. Введите курс вручную." });
        }
        updatePreview();
    }

    function updatePreview() {
        const rates = { auto: autoRate, manual: parseNumber(manualRate.value), history: historyRate };
        const rate = rates[selectedMode()];
        const value = parseNumber(amount.value);
        const visible = currency.value !== "BYN" && value > 0 && rate > 0;
        preview.textContent = visible ? `≈ ${formatMoney(value * rate)} BYN` : "";
    }

    function filterCategories() {
        const type = form.querySelector("input[name=type]:checked")?.value;
        for (const option of category.options) {
            option.hidden = Boolean(option.dataset.type) && option.dataset.type !== type;
        }
        if (category.selectedOptions[0]?.hidden) category.value = "";
    }

    currency.addEventListener("change", refreshRate);
    date.addEventListener("change", refreshRate);
    amount.addEventListener("input", updatePreview);
    manualRate.addEventListener("focus", () => { setMode("manual"); updatePreview(); });
    manualRate.addEventListener("input", updatePreview);
    form.querySelectorAll("input[name=rate_mode]").forEach((radio) => radio.addEventListener("change", updatePreview));
    form.querySelectorAll("input[name=type]").forEach((radio) => radio.addEventListener("change", filterCategories));

    filterCategories();
    // After a server-side "rate unavailable" error keep its state instead of asking again.
    if (form.dataset.rateError === "true") updatePreview();
    else refreshRate();
})();
