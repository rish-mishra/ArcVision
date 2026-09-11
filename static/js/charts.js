/* Small dependency-free SVG chart helpers. Every chart reads its palette
   from CSS custom properties so it follows the active theme automatically,
   and every value shown is one already computed by the backend -- these
   helpers only lay pixels out, they never compute or infer data. */

const Charts = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const tooltipEl = () => document.getElementById("svg-tooltip");

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function el(tag, attrs = {}) {
    const e = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    return e;
  }

  function showTooltip(evt, html) {
    const tip = tooltipEl();
    tip.innerHTML = html;
    tip.style.display = "block";
    tip.style.left = (evt.pageX + 12) + "px";
    tip.style.top = (evt.pageY + 12) + "px";
  }
  function hideTooltip() { tooltipEl().style.display = "none"; }

  const outcomeColor = (outcome) => {
    if (outcome === "made") return cssVar("--good");
    if (outcome === "missed") return cssVar("--critical");
    return cssVar("--unknown");
  };

  function emptyMessage(container, text) {
    container.innerHTML = `<div class="empty-state">${text}</div>`;
  }

  /** Vertical bar chart: one bar per shot, colored by outcome. */
  function perShotBarChart(container, { values, outcomes, unit = "", height = 220 }) {
    const valid = values.map((v, i) => ({ v, i })).filter((d) => d.v !== null && d.v !== undefined);
    if (valid.length === 0) return emptyMessage(container, "No data available for this metric.");

    const width = Math.max(container.clientWidth || 640, 320);
    const margin = { top: 16, right: 12, bottom: 28, left: 44 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;

    const vals = valid.map((d) => d.v);
    let min = Math.min(0, ...vals), max = Math.max(...vals);
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.08;
    min -= pad; max += pad;

    // Charts can be built while their tab is still hidden (every Details
    // sub-view is rendered once, upfront, on data load -- see app.js's
    // renderCoach -- not lazily on first tab click), which makes
    // container.clientWidth read 0 and fall back to the guessed design
    // width above. Setting the SVG's actual box via CSS (not just the
    // width/height attributes) means it still visually fills whatever the
    // real container width turns out to be once the tab becomes visible,
    // scaling the whole chart uniformly (no distortion) via its viewBox --
    // for a chart built while already visible, real width === design
    // width, so this is a no-op.
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, style: "width:100%;height:auto;display:block;" });
    const g = el("g", { transform: `translate(${margin.left},${margin.top})` });

    const y0 = innerH - ((0 - min) / (max - min)) * innerH;
    g.appendChild(el("line", { x1: 0, x2: innerW, y1: y0, y2: y0, stroke: cssVar("--baseline"), "stroke-width": 1 }));

    [min, (min + max) / 2, max].forEach((tickVal) => {
      const y = innerH - ((tickVal - min) / (max - min)) * innerH;
      g.appendChild(el("line", { x1: 0, x2: innerW, y1: y, y2: y, stroke: cssVar("--gridline"), "stroke-width": 1 }));
      const t = el("text", { x: -8, y: y + 4, "text-anchor": "end", "font-size": 11, fill: cssVar("--text-muted") });
      t.textContent = tickVal.toFixed(1);
      g.appendChild(t);
    });

    const bw = Math.max(6, Math.min(28, innerW / values.length - 6));
    const step = innerW / values.length;

    valid.forEach(({ v, i }) => {
      const x = i * step + step / 2 - bw / 2;
      const yv = innerH - ((v - min) / (max - min)) * innerH;
      const barY = Math.min(y0, yv), barH = Math.abs(y0 - yv);
      const color = outcomeColor(outcomes[i]);
      const rect = el("rect", {
        x, y: barY, width: bw, height: Math.max(1, barH), rx: 3, fill: color, opacity: 0.9,
      });
      rect.addEventListener("mousemove", (evt) => showTooltip(evt, `Shot ${i + 1}: <strong>${v.toFixed(2)}${unit}</strong><br>${outcomes[i]}`));
      rect.addEventListener("mouseleave", hideTooltip);
      g.appendChild(rect);
      if (values.length <= 24) {
        const lbl = el("text", { x: x + bw / 2, y: innerH + 16, "text-anchor": "middle", "font-size": 10, fill: cssVar("--text-muted") });
        lbl.textContent = i + 1;
        g.appendChild(lbl);
      }
    });

    svg.appendChild(g);
    container.innerHTML = "";
    container.appendChild(svg);
  }

  /** Strip plot comparing two groups (made vs missed) for one metric, with mean markers. */
  function madeVsMissedStrip(container, { madeValues, missedValues, unit = "", height = 150 }) {
    const all = [...madeValues, ...missedValues];
    if (all.length === 0) return emptyMessage(container, "No data available for this metric.");

    const width = Math.max(container.clientWidth || 640, 320);
    const margin = { top: 16, right: 20, bottom: 24, left: 20 };
    const innerW = width - margin.left - margin.right;
    let min = Math.min(...all), max = Math.max(...all);
    if (min === max) { min -= 1; max += 1; }
    const pad = (max - min) * 0.12;
    min -= pad; max += pad;
    const xOf = (v) => ((v - min) / (max - min)) * innerW;

    // Charts can be built while their tab is still hidden (every Details
    // sub-view is rendered once, upfront, on data load -- see app.js's
    // renderCoach -- not lazily on first tab click), which makes
    // container.clientWidth read 0 and fall back to the guessed design
    // width above. Setting the SVG's actual box via CSS (not just the
    // width/height attributes) means it still visually fills whatever the
    // real container width turns out to be once the tab becomes visible,
    // scaling the whole chart uniformly (no distortion) via its viewBox --
    // for a chart built while already visible, real width === design
    // width, so this is a no-op.
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, style: "width:100%;height:auto;display:block;" });
    const g = el("g", { transform: `translate(${margin.left},${margin.top})` });
    const rowY = { made: 34, missed: 84 };

    g.appendChild(el("text", { x: -4, y: rowY.made + 4, "font-size": 12, fill: cssVar("--good"), "font-weight": 700 }));
    const madeLabel = el("text", { x: 0, y: rowY.made - 16, "font-size": 11, fill: cssVar("--text-muted") });
    madeLabel.textContent = `MADE (n=${madeValues.length})`;
    g.appendChild(madeLabel);
    const missedLabel = el("text", { x: 0, y: rowY.missed - 16, "font-size": 11, fill: cssVar("--text-muted") });
    missedLabel.textContent = `MISSED (n=${missedValues.length})`;
    g.appendChild(missedLabel);

    function drawRow(values, y, color) {
      g.appendChild(el("line", { x1: 0, x2: innerW, y1: y, y2: y, stroke: cssVar("--gridline") }));
      values.forEach((v) => {
        const c = el("circle", { cx: xOf(v), cy: y, r: 5, fill: color, opacity: 0.75, stroke: cssVar("--surface-1"), "stroke-width": 1 });
        c.addEventListener("mousemove", (evt) => showTooltip(evt, `${v.toFixed(2)}${unit}`));
        c.addEventListener("mouseleave", hideTooltip);
        g.appendChild(c);
      });
      if (values.length) {
        const mean = values.reduce((a, b) => a + b, 0) / values.length;
        g.appendChild(el("line", { x1: xOf(mean), x2: xOf(mean), y1: y - 14, y2: y + 14, stroke: color, "stroke-width": 2 }));
      }
    }
    drawRow(madeValues, rowY.made, cssVar("--good"));
    drawRow(missedValues, rowY.missed, cssVar("--critical"));

    svg.appendChild(g);
    container.innerHTML = "";
    container.appendChild(svg);
  }

  /** Horizontal ranked bar chart (e.g. top differentiators by effect size). */
  function rankedHBar(container, { items, valueFmt = (v) => v.toFixed(2) }) {
    if (!items.length) return emptyMessage(container, "No ranked metrics available.");
    const rowH = 34;
    const height = items.length * rowH + 20;
    const width = Math.max(container.clientWidth || 640, 320);
    const margin = { top: 10, right: 60, bottom: 10, left: 200 };
    const innerW = width - margin.left - margin.right;
    const maxAbs = Math.max(...items.map((d) => Math.abs(d.value)), 0.01);

    // Charts can be built while their tab is still hidden (every Details
    // sub-view is rendered once, upfront, on data load -- see app.js's
    // renderCoach -- not lazily on first tab click), which makes
    // container.clientWidth read 0 and fall back to the guessed design
    // width above. Setting the SVG's actual box via CSS (not just the
    // width/height attributes) means it still visually fills whatever the
    // real container width turns out to be once the tab becomes visible,
    // scaling the whole chart uniformly (no distortion) via its viewBox --
    // for a chart built while already visible, real width === design
    // width, so this is a no-op.
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, style: "width:100%;height:auto;display:block;" });
    const g = el("g", { transform: `translate(${margin.left},${margin.top})` });
    const zeroX = innerW / 2;

    items.forEach((item, i) => {
      const y = i * rowH;
      const label = el("text", { x: -8, y: y + rowH / 2 + 4, "text-anchor": "end", "font-size": 12, fill: cssVar("--text-primary") });
      label.textContent = item.label;
      g.appendChild(label);

      const barW = (Math.abs(item.value) / maxAbs) * zeroX;
      const x = item.value >= 0 ? zeroX : zeroX - barW;
      const rect = el("rect", {
        x, y: y + 6, width: Math.max(1, barW), height: rowH - 14, rx: 4,
        fill: item.value >= 0 ? cssVar("--brand") : cssVar("--series-2"),
      });
      rect.addEventListener("mousemove", (evt) => showTooltip(evt, `${item.label}: <strong>${valueFmt(item.value)}</strong>`));
      rect.addEventListener("mouseleave", hideTooltip);
      g.appendChild(rect);

      const valLabel = el("text", {
        x: item.value >= 0 ? x + barW + 6 : x - 6, y: y + rowH / 2 + 4,
        "text-anchor": item.value >= 0 ? "start" : "end", "font-size": 11, fill: cssVar("--text-muted"),
      });
      valLabel.textContent = valueFmt(item.value);
      g.appendChild(valLabel);
    });

    g.appendChild(el("line", { x1: zeroX, x2: zeroX, y1: 0, y2: items.length * rowH, stroke: cssVar("--baseline") }));
    svg.appendChild(g);
    container.innerHTML = "";
    container.appendChild(svg);
  }

  /** Two-point (early vs late) line for a single metric trend. */
  function earlyLateLine(container, { early, late, unit = "", height = 140, label = "" }) {
    if (early === null || late === null || early === undefined || late === undefined) {
      return emptyMessage(container, "Not enough data for this trend.");
    }
    const width = Math.max(container.clientWidth || 400, 260);
    const margin = { top: 20, right: 60, bottom: 26, left: 20 };
    const innerW = width - margin.left - margin.right;
    const innerH = height - margin.top - margin.bottom;
    const min = Math.min(early, late), max = Math.max(early, late);
    const span = max - min || 1;
    const yOf = (v) => innerH - ((v - min + span * 0.2) / (span * 1.4)) * innerH;

    // Charts can be built while their tab is still hidden (every Details
    // sub-view is rendered once, upfront, on data load -- see app.js's
    // renderCoach -- not lazily on first tab click), which makes
    // container.clientWidth read 0 and fall back to the guessed design
    // width above. Setting the SVG's actual box via CSS (not just the
    // width/height attributes) means it still visually fills whatever the
    // real container width turns out to be once the tab becomes visible,
    // scaling the whole chart uniformly (no distortion) via its viewBox --
    // for a chart built while already visible, real width === design
    // width, so this is a no-op.
    const svg = el("svg", { width, height, viewBox: `0 0 ${width} ${height}`, style: "width:100%;height:auto;display:block;" });
    const g = el("g", { transform: `translate(${margin.left},${margin.top})` });

    const x0 = 0, x1 = innerW;
    const y0 = yOf(early), y1 = yOf(late);
    const color = late > early ? cssVar("--series-4") : cssVar("--brand");

    g.appendChild(el("line", { x1: x0, x2: x1, y1: y0, y2: y1, stroke: color, "stroke-width": 2 }));
    [[x0, y0, early, "Early"], [x1, y1, late, "Late"]].forEach(([x, y, v, lbl]) => {
      g.appendChild(el("circle", { cx: x, cy: y, r: 5, fill: color }));
      const t = el("text", { x, y: y - 12, "text-anchor": x === x0 ? "start" : "end", "font-size": 12, fill: cssVar("--text-primary"), "font-weight": 700 });
      t.textContent = `${v.toFixed(2)}${unit}`;
      g.appendChild(t);
      const t2 = el("text", { x, y: innerH + 18, "text-anchor": x === x0 ? "start" : "end", "font-size": 11, fill: cssVar("--text-muted") });
      t2.textContent = lbl;
      g.appendChild(t2);
    });

    svg.appendChild(g);
    container.innerHTML = "";
    container.appendChild(svg);
  }

  return { perShotBarChart, madeVsMissedStrip, rankedHBar, earlyLateLine, outcomeColor, emptyMessage };
})();
