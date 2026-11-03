"use strict";

const get = id => document.getElementById(id);
const config = JSON.parse(get("config").textContent);
const readings = config.cells.map(() => ({}));
const selected = () => readings[get("cell").selectedIndex];

function valid(row) {
    if (!row.mean) return !row.upper && !row.lower;
    return (!row.upper || row.upper.y < row.mean.y)
        && (!row.lower || row.lower.y > row.mean.y);
}

function paint() {
    const marks = get("marks");
    marks.replaceChildren();
    for (const [kind, point] of Object.entries(selected())) {
        const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
        circle.setAttribute("cx", point.x);
        circle.setAttribute("cy", point.y);
        circle.setAttribute("r", Math.max(2, (config.x1 - config.x0) / 180));
        circle.setAttribute("fill", kind === "mean" ? "#007ea8" : "#e45422");
        circle.setAttribute("stroke", "white");
        marks.append(circle);
    }
    const count = readings.filter(row => row.mean).length;
    const ordered = readings.every(valid);
    get("status").textContent = ordered
        ? count + " / " + readings.length + " cells marked"
        : "Each error end needs its center and must be on the corresponding side.";
    get("download").disabled = !ordered || !count || !get("reader").value.trim()
        || !get("date").value || !get("date").validity.valid;
}

for (const cell of config.cells) {
    get("cell").add(new Option(cell.join(" · ")));
}
get("plot").addEventListener("click", event => {
    const plot = get("plot");
    const point = new DOMPoint(event.clientX, event.clientY)
        .matrixTransform(plot.getScreenCTM().inverse());
    if (point.x < config.x0 - .5 || point.x >= config.x1 + .5
        || point.y < config.y0 - .5 || point.y >= config.y1 + .5) return;
    selected()[get("mark").value] = {x: Math.round(point.x), y: Math.round(point.y)};
    paint();
});
get("clear").addEventListener("click", () => {
    delete selected()[get("mark").value];
    paint();
});
for (const field of ["cell", "reader", "date"]) get(field).addEventListener("input", paint);

function csvCell(value) {
    return '"' + String(value).replaceAll('"', '""') + '"';
}

get("download").addEventListener("click", () => {
    const rows = [config.columns];
    readings.forEach((row, index) => {
        if (!row.mean) return;
        rows.push([config.id, ...config.cells[index], row.mean.x, row.mean.y,
            row.upper?.y ?? "", row.lower?.y ?? "", "PERSON",
            get("reader").value.trim(), get("date").value, config.hash, ""]);
    });
    const csv = rows.map(row => row.map(csvCell).join(",")).join("\r\n") + "\r\n";
    const url = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = "manual_readings.csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
});
paint();
