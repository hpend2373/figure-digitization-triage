"use strict";

const byId = id => document.getElementById(id);
const {key, panels} = JSON.parse(byId("data").textContent);
const storageKey = "fdt-workbench-v1:" + key;
const kinds = ["mean", "upper", "lower"];
const drafts = panels.map(panel => panel.cells.map(() => ({})));
let panelIndex = 0;
let cellIndex = 0;
let kind = "mean";
let zoom = 1;

function inside(panel, point) {
    return point && Number.isInteger(point.x) && Number.isInteger(point.y)
        && point.x >= panel.x0 && point.x <= panel.x1
        && point.y >= panel.y0 && point.y <= panel.y1;
}

try {
    const saved = JSON.parse(localStorage.getItem(storageKey));
    if (saved) {
        drafts.forEach((rows, pi) => rows.forEach((row, ci) => {
            for (const field of kinds) {
                const point = saved.drafts?.[pi]?.[ci]?.[field];
                if (inside(panels[pi], point)) row[field] = point;
            }
        }));
        byId("reader").value = saved.reader ?? "";
        byId("date").value = saved.date ?? "";
        byId("saved").textContent = "저장한 초안을 불러왔습니다";
    }
} catch {
    byId("saved").textContent = "브라우저 초안을 불러올 수 없습니다";
}

function save() {
    try {
        localStorage.setItem(storageKey, JSON.stringify({
            drafts, reader: byId("reader").value, date: byId("date").value,
        }));
        byId("saved").textContent = "이 브라우저에 초안 저장됨";
    } catch {
        byId("saved").textContent = "초안 저장을 사용할 수 없습니다. 닫기 전에 CSV를 내려받으세요.";
    }
}

const selectedPanel = () => panels[panelIndex];
const selectedRow = () => drafts[panelIndex][cellIndex];

function valid(row) {
    if (!row.mean) return !row.upper && !row.lower;
    return (!row.upper || row.upper.y < row.mean.y)
        && (!row.lower || row.lower.y > row.mean.y);
}

function preview(panel, point) {
    if (!point) return "—";
    const [[v0, p0], [v1, p1]] = panel.ticks;
    return Number((v0 + (point.y - p0) * (v1 - v0) / (p1 - p0)).toPrecision(5)).toString();
}

function setScale() {
    const panel = selectedPanel();
    const width = (byId("viewport").clientWidth || 500) * zoom;
    byId("plot").setAttribute("width", width);
    byId("plot").setAttribute("height", width * (panel.y1 - panel.y0 + 1) / (panel.x1 - panel.x0 + 1));
    byId("fit").textContent = Math.round(zoom * 100) + "% · 맞춤";
}

function pickPanel(index) {
    panelIndex = index;
    cellIndex = 0;
    zoom = 1;
    const panel = selectedPanel();
    const box = [panel.x0 - .5, panel.y0 - .5, panel.x1 - panel.x0 + 1, panel.y1 - panel.y0 + 1];
    byId("plot").setAttribute("viewBox", box.join(" "));
    const raster = byId("raster");
    ["x", "y", "width", "height"].forEach((attr, i) => raster.setAttribute(attr, box[i]));
    raster.setAttribute("href", "data:image/png;base64," + panel.image);
    byId("panel-title").textContent = panel.outcome || panel.id;
    byId("axis").textContent = [
        panel.id, panel.unit, panel.bar_top,
        "축 교정 " + panel.ticks.map(([value, pixel]) => value + " @ " + pixel + " px").join(" / "),
    ].filter(Boolean).join(" · ");
    [...byId("panels").children].forEach((button, i) =>
        button.setAttribute("aria-pressed", i === index));
    byId("viewport").scrollTo(0, 0);
    setScale();
    paint();
}

function paint() {
    const panel = selectedPanel();
    const rows = drafts[panelIndex];
    const grid = byId("cells");
    const marks = byId("marks");
    grid.replaceChildren();
    marks.replaceChildren();
    panel.cells.forEach((cell, i) => {
        const tr = grid.insertRow();
        const button = document.createElement("button");
        button.textContent = cell.join(" · ");
        button.setAttribute("aria-pressed", i === cellIndex);
        button.onclick = () => {
            cellIndex = i;
            paint();
            grid.rows[i].querySelector("button").focus();
        };
        tr.insertCell().append(button);
        for (const field of kinds) {
            const point = rows[i][field];
            const td = tr.insertCell();
            td.textContent = preview(panel, point);
            if (!point) continue;
            td.title = point.x + ", " + point.y + " px";
            const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
            circle.setAttribute("cx", point.x);
            circle.setAttribute("cy", point.y);
            circle.setAttribute("r", (panel.x1 - panel.x0) / 145);
            circle.setAttribute("fill", field === "mean" ? "#087d99" : "#d95728");
            circle.setAttribute("opacity", i === cellIndex ? "1" : ".42");
            circle.setAttribute("stroke", "white");
            marks.append(circle);
        }
    });
    const all = drafts.flat();
    const count = all.filter(row => row.mean).length;
    byId("count").textContent = count + " / " + all.length + " 셀 입력 · " + panel.cells[cellIndex].join(" · ");
    const ordered = all.every(valid);
    const reader = byId("reader").value.trim();
    const date = byId("date");
    byId("status").textContent = ordered
        ? "내보내기에는 값 위치를 입력한 셀만 포함됩니다."
        : "오차막대 끝은 값 위치가 필요하며, 각각 위쪽과 아래쪽에 있어야 합니다.";
    byId("download").disabled = !ordered || !count || !reader || !date.value || !date.validity.valid;
}

panels.forEach((panel, i) => {
    const button = document.createElement("button");
    button.textContent = panel.outcome || panel.id;
    button.title = panel.id;
    button.onclick = () => pickPanel(i);
    byId("panels").append(button);
});
for (const button of document.querySelectorAll("[data-mark]")) {
    button.onclick = () => {
        kind = button.dataset.mark;
        for (const item of document.querySelectorAll("[data-mark]")) {
            item.setAttribute("aria-pressed", item === button);
        }
    };
}
byId("plot").onclick = event => {
    const matrix = byId("plot").getScreenCTM();
    if (!matrix) return;
    const local = new DOMPoint(event.clientX, event.clientY).matrixTransform(matrix.inverse());
    const point = {x: Math.round(local.x), y: Math.round(local.y)};
    if (!inside(selectedPanel(), point)) return;
    selectedRow()[kind] = point;
    save();
    paint();
};
byId("clear").onclick = () => {
    delete selectedRow()[kind];
    save();
    paint();
};
byId("plus").onclick = () => { zoom = Math.min(6, zoom * 1.25); setScale(); };
byId("minus").onclick = () => { zoom = Math.max(.5, zoom / 1.25); setScale(); };
byId("fit").onclick = () => { zoom = 1; setScale(); };
new ResizeObserver(setScale).observe(byId("viewport"));
for (const id of ["reader", "date"]) byId(id).oninput = () => { save(); paint(); };

byId("download").onclick = () => {
    const rows = [panels[0].columns];
    panels.forEach((panel, pi) => drafts[pi].forEach((row, ci) => {
        if (!row.mean) return;
        rows.push([panel.id, ...panel.cells[ci], row.mean.x, row.mean.y,
            row.upper?.y ?? "", row.lower?.y ?? "", "PERSON",
            byId("reader").value.trim(), byId("date").value, panel.hash, ""]);
    }));
    const csv = rows.map(row => row.map(value => '"' +
        String(value).replaceAll('"', '""') + '"').join(",")).join("\r\n") + "\r\n";
    const url = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"}));
    const link = document.createElement("a");
    link.href = url;
    link.download = "manual_readings.csv";
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
};

pickPanel(0);
