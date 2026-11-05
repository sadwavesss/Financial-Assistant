// Analytics charts: expense structure (doughnut) and income/expense dynamics (bars + balance line).
(() => {
    const source = document.getElementById("analytics-data");
    if (!source || typeof Chart === "undefined") return;
    const data = JSON.parse(source.textContent);

    const money = (value) =>
        `${value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} BYN`;
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.maintainAspectRatio = false;

    const total = data.structure.values.reduce((sum, value) => sum + value, 0);
    new Chart(document.getElementById("structure-chart"), {
        type: "doughnut",
        data: {
            labels: data.structure.labels,
            datasets: [{ data: data.structure.values, backgroundColor: data.structure.colors, borderWidth: 1 }],
        },
        options: {
            cutout: "60%",
            plugins: {
                legend: { position: "right", labels: { boxWidth: 12 } },
                tooltip: {
                    callbacks: {
                        label: (item) => ` ${item.label}: ${money(item.raw)} (${((item.raw / total) * 100).toFixed(1)}%)`,
                    },
                },
            },
        },
    });

    new Chart(document.getElementById("dynamics-chart"), {
        data: {
            labels: data.dynamics.labels,
            datasets: [
                { type: "bar", label: "Доходы", data: data.dynamics.income, backgroundColor: "rgba(25, 135, 84, 0.7)" },
                { type: "bar", label: "Расходы", data: data.dynamics.expense, backgroundColor: "rgba(220, 53, 69, 0.7)" },
                {
                    type: "line", label: "Баланс", data: data.dynamics.balance,
                    borderColor: "#0d6efd", backgroundColor: "#0d6efd", tension: 0.3, pointRadius: 2,
                },
            ],
        },
        options: {
            interaction: { mode: "index", intersect: false },
            scales: { y: { ticks: { callback: (value) => value.toLocaleString("ru-RU") } } },
            plugins: { tooltip: { callbacks: { label: (item) => ` ${item.dataset.label}: ${money(item.raw)}` } } },
        },
    });
})();
