// Forecast chart: actual expenses, forecast (dashed) and the 80 % interval as a shaded band.
(() => {
    const source = document.getElementById("forecast-data");
    if (!source || typeof Chart === "undefined") return;
    const data = JSON.parse(source.textContent);
    const money = (value) =>
        `${value.toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} BYN`;

    new Chart(document.getElementById("forecast-chart"), {
        type: "line",
        data: {
            labels: data.labels,
            datasets: [
                // The band is drawn between "upper" and the "lower" dataset right after it.
                { label: "Верхняя граница", data: data.upper, borderWidth: 0, pointRadius: 0,
                  backgroundColor: "rgba(13, 110, 253, 0.12)", fill: "+1" },
                { label: "Нижняя граница", data: data.lower, borderWidth: 0, pointRadius: 0, fill: false },
                { label: "Факт", data: data.actual, borderColor: "#dc3545", backgroundColor: "#dc3545",
                  tension: 0.25, pointRadius: 2 },
                { label: "Прогноз", data: data.forecast, borderColor: "#0d6efd", backgroundColor: "#0d6efd",
                  borderDash: [6, 4], tension: 0.25, pointRadius: 3 },
            ],
        },
        options: {
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            scales: { y: { beginAtZero: true, ticks: { callback: (value) => value.toLocaleString("ru-RU") } } },
            plugins: {
                legend: { labels: { filter: (item) => !item.text.includes("граница") } },
                tooltip: {
                    filter: (item) => item.raw !== null,
                    callbacks: { label: (item) => ` ${item.dataset.label}: ${money(item.raw)}` },
                },
            },
        },
    });
})();
