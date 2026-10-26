/* Interactive dashboard renderer (see app/reporting/interactive.py).
   Data values are always written as text (textContent), never as HTML. */
(async function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const make = (tag, cls, text) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined && text !== null) n.textContent = text;
    return n;
  };

  async function decode() {
    const b64 = $("data").textContent.trim();
    const bin = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
    const stream = new Blob([bin]).stream().pipeThrough(new DecompressionStream("gzip"));
    return JSON.parse(await new Response(stream).text());
  }
  let P;
  try {
    P = await decode();
  } catch (error) {
    $("loading").textContent =
      "This dashboard needs a recent browser (Chrome, Edge, Firefox 113 or Safari 16.4 or later).";
    return;
  }
  $("loading").remove();

  // ---------- data
  const F = {};
  for (const [name, t] of Object.entries(P.facts)) {
    const cols = {};
    for (const [c, v] of Object.entries(t.columns)) {
      cols[c] = v.n ? { num: true, a: v.n } : { num: false, d: v.d, i: v.i };
    }
    F[name] = { n: t.rows, cols };
  }
  const text = (t, c, i) => {
    const col = F[t].cols[c];
    if (!col) return "";
    if (col.num) return col.a[i] === null ? "" : String(col.a[i]);
    return col.d[col.i[i]];
  };
  const raw = (t, c, i) => {
    const col = F[t].cols[c];
    if (!col) return null;
    return col.num ? col.a[i] : col.d[col.i[i]];
  };
  const M = {};
  for (const [t, ms] of Object.entries(P.measures)) {
    M[t] = {};
    ms.forEach((m) => (M[t][m.key] = m));
  }
  const measure = (t, key) => (M[t] && M[t][key]) || { key, label: key, fmt: "int" };

  // ---------- formatting
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const label = (v) => {
    const s = String(v);
    const m = /^(\d{4})-(\d{2})$/.exec(s);
    return m ? MONTHS[+m[2] - 1] + "-" + m[1].slice(2) : s;
  };
  const int = (v) => Math.round(v).toLocaleString("en-US");
  const compact = (v) => {
    const a = Math.abs(v);
    if (a >= 1e9) return (v / 1e9).toFixed(2) + " B";
    if (a >= 1e6) return (v / 1e6).toFixed(1) + " M";
    if (a >= 1e4) return (v / 1e3).toFixed(0) + " K";
    return int(v);
  };
  function fmt(v, f, short) {
    if (v === null || v === undefined || (typeof v === "number" && !isFinite(v))) return "—";
    if (f === "text") return String(v);
    if (f === "pct") return (100 * v).toFixed(1) + "%";
    if (f === "change") return (v < 0 ? "Reduction " : "Increase ") + (100 * Math.abs(v)).toFixed(1) + "%";
    if (f === "num") return v.toLocaleString("en-US", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
    if (f === "days") return v.toLocaleString("en-US", { maximumFractionDigits: 1 });
    if (f === "rwf") return short ? "RWF " + compact(v) : (v < 0 ? "(" + int(-v) + ")" : int(v));
    return short ? compact(v) : int(v);
  }
  const natural = (a, b) => String(a).localeCompare(String(b), "en", { numeric: true });

  // ---------- filters
  const S = {};
  const rank = {};
  const box = $("filters");
  const selects = {};
  for (const f of P.filters) {
    const seen = new Set();
    for (const t of Object.keys(F)) {
      const col = F[t].cols[f.field];
      if (!col) continue;
      if (col.num) col.a.forEach((v) => v !== null && seen.add(String(v)));
      else col.d.forEach((v) => v !== "" && seen.add(v));
    }
    let values = [...seen];
    if (f.order === "given" && f.values) values = f.values.filter((v) => seen.has(v));
    else values.sort(natural);
    const wrap = make("label", "fl");
    wrap.append(make("span", null, f.label));
    const sel = make("select");
    sel.append(new Option(f.all_label || "All", ""));
    values.forEach((v) => sel.append(new Option(label(v), v)));
    sel.addEventListener("change", () => {
      S[f.field] = sel.value;
      render();
    });
    wrap.append(sel);
    box.append(wrap);
    selects[f.field] = sel;
  }
  const reset = make("button", "reset", "Reset filters");
  reset.type = "button";
  reset.addEventListener("click", () => {
    for (const [k, sel] of Object.entries(selects)) {
      sel.value = "";
      S[k] = "";
    }
    render();
  });
  box.append(reset);

  function predicates(t, ignore) {
    const out = [];
    for (const f of P.filters) {
      const v = S[f.field];
      if (!v || (ignore || []).includes(f.field)) continue;
      const col = F[t].cols[f.field];
      if (!col) continue;
      if (col.num) out.push((i) => String(col.a[i]) === v);
      else {
        const k = col.d.indexOf(v);
        out.push((i) => col.i[i] === k);
      }
    }
    return out;
  }
  function whereFn(t, where) {
    const col = F[t].cols[where[0]];
    if (!col) return () => false;
    if (col.num) {
      const ok = new Set(where[1].map(String));
      return (i) => ok.has(String(col.a[i]));
    }
    const ok = new Set(where[1].map((v) => col.d.indexOf(v)).filter((k) => k >= 0));
    return (i) => ok.has(col.i[i]);
  }

  // ---------- aggregation
  function aggregate(t, keyFn, ignore) {
    const ms = Object.values(M[t] || {});
    const base = ms.filter((m) => m.sum || m.count || m.distinct);
    const derived = ms.filter((m) => m.ratio || m.diff || m.complement);
    const wh = base.map((m) => (m.where ? whereFn(t, m.where) : null));
    const cols = base.map((m) => F[t].cols[m.sum || m.distinct] || null);
    const preds = predicates(t, ignore);
    const groups = new Map();
    const n = F[t].n;
    for (let i = 0; i < n; i++) {
      let ok = true;
      for (const p of preds) {
        if (!p(i)) {
          ok = false;
          break;
        }
      }
      if (!ok) continue;
      const k = keyFn(i);
      if (k === null) continue;
      let g = groups.get(k);
      if (!g) {
        g = { acc: new Float64Array(base.length), sets: base.map((m) => (m.distinct ? new Set() : null)) };
        groups.set(k, g);
      }
      for (let j = 0; j < base.length; j++) {
        if (wh[j] && !wh[j](i)) continue;
        const m = base[j];
        if (m.count) g.acc[j] += 1;
        else if (m.sum) {
          const c = cols[j];
          const v = c && c.num ? c.a[i] : null;
          if (v !== null) g.acc[j] += v;
        } else if (cols[j]) {
          const c = cols[j];
          g.sets[j].add(c.num ? c.a[i] : c.i[i]);
        }
      }
    }
    const out = new Map();
    for (const [k, g] of groups) {
      const r = {};
      base.forEach((m, j) => (r[m.key] = m.distinct ? g.sets[j].size : g.acc[j]));
      for (const m of derived) {
        if (m.ratio) {
          const a = r[m.ratio[0]];
          const b = r[m.ratio[1]];
          r[m.key] = b ? a / b : null;
        } else if (m.complement) {
          const a = r[m.complement];
          r[m.key] = a === null || a === undefined ? null : 1 - a;
        } else {
          const a = r[m.diff[0]];
          const b = r[m.diff[1]];
          r[m.key] = a === null || b === null || a === undefined || b === undefined ? null : a - b;
        }
      }
      out.set(k, r);
    }
    return out;
  }
  const total = (t, ignore) => aggregate(t, () => "", ignore).get("") || {};

  // ---------- layout
  const COLORS = ["#0079BF", "#C55A11", "#2F6B4F", "#B23A2E", "#F7BC15", "#6B4E9B", "#7A1F1F", "#5E5E5E", "#7FB8DD", "#9AA5B1"];
  const RED = "#B23A2E", AMBER = "#C55A11", GREEN = "#2F6B4F";
  if (window.Chart) {
    Chart.defaults.font.family = "-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif";
    Chart.defaults.color = "#4A5568";
    Chart.defaults.borderColor = "#EAEAE4";
    Chart.defaults.maintainAspectRatio = false;
  }
  const holder = $("sections");
  const views = [];
  P.sections.forEach((s, si) => {
    const sec = make("section", "sec");
    const head = make("div", "sech");
    head.append(make("h2", null, s.title));
    if (s.rank && s.rank.length) {
      const wrap = make("label", "rank");
      wrap.append(make("span", null, "Rank by "));
      const sel = make("select");
      const t = (s.blocks[0] || {}).facts;
      s.rank.forEach((k) => sel.append(new Option(measure(t, k).label, k)));
      rank[si] = s.rank[0];
      sel.addEventListener("change", () => {
        rank[si] = sel.value;
        render();
      });
      wrap.append(sel);
      head.append(wrap);
    }
    sec.append(head);
    if (s.note) sec.append(make("p", "note", s.note));
    const grid = make("div", "grid");
    s.blocks.forEach((b) => {
      const card = make("div", "card" + (b.type === "chart" ? "" : " wide"));
      card.append(make("h3", null, b.title));
      if (b.note) card.append(make("p", "cap", b.note));
      let body;
      if (b.type === "chart") {
        body = make("div", "cw");
        const canvas = document.createElement("canvas");
        body.append(canvas);
        views.push({ b, si, canvas, body });
      } else {
        if (b.type === "detail") {
          const bar = make("div", "dbar");
          const search = make("input");
          search.type = "search";
          search.placeholder = "Search these lines";
          search.setAttribute("aria-label", "Search " + b.title);
          const count = make("span", "cap");
          const csv = make("button", "csv", "Download CSV");
          csv.type = "button";
          bar.append(search, count, csv);
          card.append(bar);
          b._search = search;
          b._count = count;
          b._csv = csv;
          search.addEventListener("input", render);
        }
        body = make("div", "tw");
        const table = make("table", "tb");
        body.append(table);
        views.push({ b, si, table });
      }
      card.append(body);
      grid.append(card);
    });
    sec.append(grid);
    holder.append(sec);
  });

  // ---------- renderers
  const charts = new Map();
  function sortKeys(entries, b, si) {
    const by = b.sort_by === "rank" ? rank[si] : b.sort_by;
    if (b.sort === "desc" || b.sort === "asc" || (b.type === "table" && by)) {
      const dir = b.sort === "asc" || b.descending === false ? 1 : -1;
      entries.sort((x, y) => {
        const a = x[1][by];
        const c = y[1][by];
        if (a === c) return natural(x[0], y[0]);
        if (a === null || a === undefined) return 1;
        if (c === null || c === undefined) return -1;
        return dir * (a - c);
      });
    } else entries.sort((x, y) => natural(x[0], y[0]));
    return b.limit ? entries.slice(0, b.limit) : entries;
  }

  function drawChart(v) {
    const b = v.b;
    const t = b.facts;
    if (!window.Chart) return;
    const pct = (x) => (x === null || x === undefined ? null : b.percent ? 100 * x : x);
    let labels;
    let datasets;
    const ms = b.measures.map((k) => measure(t, k === "rank" ? rank[v.si] : k));
    if (b.kind === "stacked" && b.stack) {
      const by = b.sort_by === "rank" ? rank[v.si] : b.sort_by || b.measures[0];
      const tops = [...aggregate(t, (i) => text(t, b.stack, i), b.ignore)]
        .filter((e) => e[0] !== "")
        .sort((x, y) => (y[1][by] || 0) - (x[1][by] || 0) || natural(x[0], y[0]))
        .slice(0, b.stack_limit || 8)
        .filter((e) => (e[1][by] || 0) > 0)
        .map((e) => e[0]);
      const keep = new Set(tops);
      const cells = aggregate(
        t,
        (i) => {
          const s = text(t, b.stack, i);
          return keep.has(s) ? text(t, b.group, i) + "\u0001" + s : null;
        },
        b.ignore,
      );
      const groups = [...new Set([...aggregate(t, (i) => text(t, b.group, i), b.ignore).keys()])].sort(natural);
      labels = groups.map(label);
      datasets = tops.map((s, j) => ({
        label: s.length > 34 ? s.slice(0, 33) + "…" : s,
        data: groups.map((g) => pct((cells.get(g + "\u0001" + s) || {})[by] || 0)),
        backgroundColor: COLORS[j % COLORS.length],
      }));
    } else {
      const entries = sortKeys([...aggregate(t, (i) => text(t, b.group, i), b.ignore)], b, v.si);
      labels = entries.map((e) => {
        const s = label(e[0]);
        return s.length > 34 ? s.slice(0, 33) + "…" : s;
      });
      datasets = ms.map((m, j) => {
        const data = entries.map((e) => pct(e[1][m.key]));
        const line = b.kind === "line" || (b.kind === "combo" && j > 0);
        const color = COLORS[j % COLORS.length];
        const ds = {
          label: m.label,
          data,
          type: line ? "line" : "bar",
          borderColor: color,
          backgroundColor: color,
          tension: 0.25,
          yAxisID: b.kind === "combo" && j > 0 ? "y1" : "y",
        };
        if (b.kind === "hbar" && b.traffic && ms.length === 1) {
          ds.backgroundColor = entries.map((e) => {
            const x = e[1][m.key];
            return x === null ? "#9AA5B1" : x < b.traffic[0] ? RED : x < b.traffic[1] ? AMBER : GREEN;
          });
        }
        return ds;
      });
    }
    const f0 = ms[0] ? ms[0].fmt : "int";
    const tick = (val, f) => (b.percent || f === "pct" ? val + "%" : fmt(val, f, true));
    const scales = {};
    const valueAxis = {
      ticks: { callback: (val) => tick(val, f0), precision: f0 === "int" ? 0 : undefined },
      beginAtZero: true,
    };
    if (b.percent) valueAxis.max = 100;
    if (b.kind === "hbar") {
      scales.x = valueAxis;
      scales.y = { ticks: { autoSkip: false } };
    } else {
      scales.y = valueAxis;
      scales.x = { stacked: b.kind === "stacked", ticks: { autoSkip: labels.length > 14, maxRotation: 50 } };
      if (b.kind === "stacked") scales.y.stacked = true;
      if (b.kind === "combo") {
        const f1 = ms[1] ? ms[1].fmt : "pct";
        scales.y.ticks = { callback: (val) => fmt(val, f0, true) };
        delete scales.y.max;
        scales.y1 = {
          position: "right",
          grid: { display: false },
          beginAtZero: true,
          ticks: { callback: (val) => (f1 === "pct" ? val + "%" : fmt(val, f1, true)) },
        };
        datasets.forEach((d, j) => {
          if (j > 0 && f1 === "pct") d.data = d.data.map((x) => (x === null ? null : 100 * x));
        });
        if (f1 === "pct") scales.y1.max = 100;
      }
    }
    const height = b.kind === "hbar" ? Math.max(220, labels.length * 24 + 50) : 320;
    v.body.style.height = height + "px";
    const old = charts.get(v.canvas);
    if (old) old.destroy();
    charts.set(
      v.canvas,
      new Chart(v.canvas, {
        type: b.kind === "hbar" || b.kind === "stacked" ? "bar" : b.kind === "line" ? "line" : "bar",
        data: { labels, datasets },
        options: {
          indexAxis: b.kind === "hbar" ? "y" : "x",
          animation: false,
          plugins: {
            legend: { display: datasets.length > 1, position: "bottom", labels: { boxWidth: 10 } },
            tooltip: {
              callbacks: {
                label: (c) => {
                  const m = ms[Math.min(c.datasetIndex, ms.length - 1)] || ms[0];
                  const pctShown = b.percent || (b.kind === "combo" && c.datasetIndex > 0 && m.fmt === "pct");
                  const value = pctShown ? (c.raw === null ? "—" : c.raw.toFixed(1) + "%") : fmt(c.raw, m.fmt);
                  return c.dataset.label + ": " + value;
                },
              },
            },
          },
          scales,
        },
      }),
    );
  }

  function cellText(value, f) {
    return fmt(value, f, false);
  }
  function addBar(td, value, traffic) {
    if (value === null || value === undefined) {
      td.textContent = "—";
      return;
    }
    const bar = make("span", "bar");
    const fill = make("i");
    fill.style.width = Math.max(0, Math.min(100, 100 * value)) + "%";
    fill.style.background = value < traffic[0] ? RED : value < traffic[1] ? AMBER : GREEN;
    bar.append(fill);
    td.append(bar, document.createTextNode((100 * value).toFixed(1) + "%"));
  }

  function drawTable(v) {
    const b = v.b;
    const t = b.facts;
    const table = v.table;
    table.replaceChildren();
    const thead = make("thead");
    const hr = make("tr");
    const ms = b.columns.map((k) => measure(t, k));
    b.group.forEach((g) => hr.append(make("th", null, (b.labels && b.labels[g]) || g)));
    ms.forEach((m) => hr.append(make("th", "n", m.label)));
    thead.append(hr);
    const keyFn = (i) => b.group.map((g) => text(t, g, i)).join("\u0001");
    const entries = sortKeys([...aggregate(t, keyFn, b.ignore)], { ...b, type: "table" }, v.si);
    const tbody = make("tbody");
    entries.forEach(([k, r]) => {
      const tr = make("tr");
      k.split("\u0001").forEach((part) => tr.append(make("td", null, label(part) || "—")));
      ms.forEach((m) => {
        const td = make("td", "n");
        if ((b.bars || []).includes(m.key)) addBar(td, r[m.key], b.traffic || [0.85, 0.95]);
        else td.textContent = cellText(r[m.key], m.fmt);
        tr.append(td);
      });
      tbody.append(tr);
    });
    if (!entries.length) {
      const tr = make("tr");
      const td = make("td", "muted", "Nothing under the current filters.");
      td.colSpan = b.group.length + ms.length;
      tr.append(td);
      tbody.append(tr);
    }
    const tot = total(t, b.ignore);
    const tf = make("tfoot");
    const fr = make("tr");
    b.group.forEach((g, j) => fr.append(make("td", null, j === 0 ? "Total" : "")));
    ms.forEach((m) => fr.append(make("td", "n", cellText(tot[m.key], m.fmt))));
    tf.append(fr);
    table.append(thead, tbody, tf);
  }

  function detailRows(b) {
    const t = b.facts;
    const preds = predicates(t, []);
    const q = (b._search.value || "").trim().toLowerCase();
    const rows = [];
    for (let i = 0; i < F[t].n; i++) {
      let ok = true;
      for (const p of preds) {
        if (!p(i)) {
          ok = false;
          break;
        }
      }
      if (!ok) continue;
      if (q && !b.columns.some(([c]) => text(t, c, i).toLowerCase().includes(q))) continue;
      rows.push(i);
    }
    if (b.sort_by) {
      const dir = b.descending === false ? 1 : -1;
      rows.sort((x, y) => {
        const a = raw(t, b.sort_by, x);
        const c = raw(t, b.sort_by, y);
        const aEmpty = a === null || a === undefined || a === "";
        const cEmpty = c === null || c === undefined || c === "";
        if (aEmpty || cEmpty) return aEmpty === cEmpty ? x - y : aEmpty ? 1 : -1;
        if (typeof a === "number" && typeof c === "number") return dir * (a - c) || x - y;
        return dir * natural(a ?? "", c ?? "") || x - y;
      });
    }
    return rows;
  }
  function drawDetail(v) {
    const b = v.b;
    const t = b.facts;
    const rows = detailRows(b);
    const table = v.table;
    table.replaceChildren();
    const hr = make("tr");
    b.columns.forEach(([, h, f]) => hr.append(make("th", f === "text" ? null : "n", h)));
    const thead = make("thead");
    thead.append(hr);
    const tbody = make("tbody");
    rows.slice(0, b.limit || 100).forEach((i) => {
      const tr = make("tr");
      b.columns.forEach(([c, , f]) => {
        const value = raw(t, c, i);
        tr.append(make("td", f === "text" ? null : "n", f === "text" ? label(value ?? "") : cellText(value, f)));
      });
      tbody.append(tr);
    });
    table.append(thead, tbody);
    const shown = Math.min(rows.length, b.limit || 100);
    b._count.textContent =
      rows.length > shown
        ? int(shown) + " of " + int(rows.length) + " lines shown; the CSV has them all"
        : int(rows.length) + " lines";
    b._csv.onclick = () => {
      const quote = (s) => '"' + String(s).replace(/"/g, '""') + '"';
      const lines = [b.columns.map(([, h]) => quote(h)).join(",")];
      rows.forEach((i) => lines.push(b.columns.map(([c]) => quote(text(t, c, i))).join(",")));
      const blob = new Blob(["﻿" + lines.join("\r\n")], { type: "text/csv;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = b.title.replace(/[^A-Za-z0-9]+/g, "_") + ".csv";
      document.body.append(a);
      a.click();
      a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 1000);
    };
  }

  function drawKpis() {
    const box = $("kpis");
    box.replaceChildren();
    const cache = {};
    for (const k of P.kpis) {
      const r = cache[k.facts] || (cache[k.facts] = total(k.facts, []));
      const m = measure(k.facts, k.measure);
      const tile = make("div", "kpi tone-" + (k.tone || "blue"));
      tile.append(make("div", "l", k.label), make("div", "v", fmt(r[k.measure], m.fmt, true)));
      if (k.note) {
        const note = k.note.replace(/\{([A-Za-z0-9_]+)\}/g, (_, key) => fmt(r[key], measure(k.facts, key).fmt, true));
        tile.append(make("div", "s", note));
      }
      box.append(tile);
    }
  }

  function drawActive() {
    const parts = P.filters.filter((f) => S[f.field]).map((f) => f.label + ": " + label(S[f.field]));
    $("active").textContent = parts.length ? "Filters: " + parts.join(" · ") : "Showing all data (no filters).";
  }

  function render() {
    drawActive();
    drawKpis();
    for (const v of views) {
      if (v.b.type === "chart") drawChart(v);
      else if (v.b.type === "table") drawTable(v);
      else drawDetail(v);
    }
  }
  render();
})();
