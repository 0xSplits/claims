// Shared flowchart renderer. Declarative nodes on a (col,row) grid, bezier edges, status classes for both themes.
// nodes: { id, label, col, row, type: process|decision|terminal|lane-note, status: added|changed|removed|same|gap|deferred, href, detail }
// edges: { from, to, label, status: same|added|removed|covered|uncovered|async|gap, detail, test }
window.Flow = (() => {
  const NS = 'http://www.w3.org/2000/svg';
  const el = (tag, attrs = {}, text) => { const e = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => v !== undefined && e.setAttribute(k, v)); if (text !== undefined) e.textContent = text; return e; };
  const COLORS = { same: 'var(--muted)', added: 'var(--accent)', changed: 'var(--warn)', removed: 'var(--bad)', gap: 'var(--bad)', deferred: 'var(--warn)', covered: 'var(--ok)', uncovered: 'var(--bad)', async: 'var(--prev, var(--muted))', faint: 'var(--line)' };

  function render(svg, { nodes, edges, lanes = [], regions = [], colW = 230, rowH = 100, nodeW = 196, nodeH = 54, pad = 24, laneTop = 0, onSelect }) {
    svg.innerHTML = '';
    const maxCol = Math.max(...nodes.map((n) => n.col)), maxRow = Math.max(...nodes.map((n) => n.row));
    const W = pad * 2 + maxCol * colW + nodeW, H = pad * 2 + laneTop + maxRow * rowH + nodeH;
    svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.style.minWidth = Math.min(W, 1100) + 'px'; svg.style.aspectRatio = `${W} / ${H}`;
    const defs = el('defs');
    Object.entries(COLORS).forEach(([k, c]) => { const m = el('marker', { id: 'arr-' + k, viewBox: '0 0 10 10', refX: 9, refY: 5, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' }); m.appendChild(el('path', { d: 'M0,0 L10,5 L0,10 z', fill: c })); defs.appendChild(m); });
    svg.appendChild(defs);
    const cx = (n) => pad + n.col * colW + nodeW / 2, cy = (n) => pad + laneTop + n.row * rowH + nodeH / 2;
    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    // lanes
    lanes.forEach((l, i) => {
      const x0 = pad + l.cols[0] * colW - 12, x1 = pad + l.cols[1] * colW + nodeW + 12;
      const g = el('g', { class: 'lane' });
      g.appendChild(el('rect', { x: x0, y: 4, width: x1 - x0, height: H - 8, rx: 8, fill: i % 2 ? 'var(--lane-b)' : 'var(--lane-a)', stroke: 'var(--line)' }));
      g.appendChild(el('text', { x: (x0 + x1) / 2, y: 22, 'text-anchor': 'middle', class: 'lane-label' }, l.label));
      svg.appendChild(g);
    });
    // regions: dashed boxes around a block of steps (a transaction, a "must agree" pair)
    (regions || []).forEach((r) => {
      const x0 = pad + r.cols[0] * colW - 10, x1 = pad + r.cols[1] * colW + nodeW + 10;
      const y0 = pad + laneTop + r.rows[0] * rowH - 10, y1 = pad + laneTop + r.rows[1] * rowH + nodeH + 10;
      const g = el('g', { class: 'region' });
      g.appendChild(el('rect', { x: x0, y: y0, width: x1 - x0, height: y1 - y0, rx: 10, fill: r.fill || 'var(--region-fill)', stroke: r.stroke || 'var(--accent)', 'stroke-dasharray': '6 4', 'stroke-width': 1.5 }));
      g.appendChild(el('text', { x: x0 + 10, y: y0 - 6, class: 'region-label', fill: r.stroke || 'var(--accent)' }, r.label));
      svg.appendChild(g);
    });
    // edges
    const eg = el('g', { class: 'edges' }); svg.appendChild(eg);
    edges.forEach((e) => {
      const a = byId[e.from], b = byId[e.to]; if (!a || !b) return;
      const ax = cx(a), ay = cy(a), bx = cx(b), by = cy(b);
      let d, lx, ly;
      const ah = a.type === 'decision' ? nodeH / 2 + 10 : nodeH / 2, bh = b.type === 'decision' ? nodeH / 2 + 10 : nodeH / 2;
      if (b.row > a.row && Math.abs(b.col - a.col) <= 2) {
        const y0 = ay + ah, y1 = by - bh, my = (y0 + y1) / 2;
        d = `M${ax},${y0} C${ax},${my} ${bx},${my} ${bx},${y1}`; lx = (ax + bx) / 2; ly = my;
      } else if (b.row === a.row) {
        const dir = bx > ax ? 1 : -1, x0 = ax + dir * nodeW / 2, x1 = bx - dir * nodeW / 2, mx = (x0 + x1) / 2;
        d = `M${x0},${ay} C${mx},${ay} ${mx},${by} ${x1},${by}`; lx = mx; ly = ay - 10;
      } else if (b.row < a.row) {
        const x0 = ax + nodeW / 2, x1 = bx + nodeW / 2, bulge = Math.max(x0, x1) + 48;
        d = `M${x0},${ay} C${bulge},${ay} ${bulge},${by} ${x1},${by}`; lx = bulge + 4; ly = (ay + by) / 2;
      } else {
        const dir = bx > ax ? 1 : -1, x0 = ax + dir * nodeW / 2, y1 = by - bh;
        d = `M${x0},${ay} C${bx},${ay} ${bx},${(ay + y1) / 2} ${bx},${y1}`; lx = (x0 + bx) / 2; ly = ay - 10;
      }
      const st = e.status || 'same', color = COLORS[st] || COLORS.same;
      const g = el('g', { class: 'edge ' + st, 'data-from': e.from, 'data-to': e.to });
      if (e.dim) g.setAttribute('opacity', '.32');
      g.appendChild(el('path', { d, fill: 'none', stroke: 'transparent', 'stroke-width': 14 }));
      const p = el('path', { d, fill: 'none', stroke: color, 'stroke-width': st === 'same' ? 1.5 : 2.25, 'marker-end': `url(#arr-${st})` });
      if (st === 'uncovered' || st === 'removed' || st === 'async' || st === 'gap') p.setAttribute('stroke-dasharray', st === 'async' ? '2 5' : '6 5');
      g.appendChild(p);
      if (e.label) { const t = el('text', { x: lx, y: ly + 4, 'text-anchor': 'middle', class: 'edge-label', fill: color }, e.label); g.appendChild(t); }
      if (e.detail || e.test) { const title = el('title'); title.textContent = [e.detail, e.test ? 'Test: ' + e.test : ''].filter(Boolean).join('\n'); g.appendChild(title); }
      if (onSelect) { g.style.cursor = 'pointer'; g.addEventListener('click', () => onSelect({ kind: 'edge', ...e })); }
      eg.appendChild(g);
    });
    // fit edge label backgrounds after text measured
    requestAnimationFrame(() => eg.querySelectorAll('text.edge-label').forEach((t) => { try { const bb = t.getBBox(); const r = el('rect', { x: bb.x - 4, y: bb.y - 2, width: bb.width + 8, height: bb.height + 4, rx: 3, fill: 'var(--panel)', class: 'edge-label-bg' }); t.parentNode.insertBefore(r, t); } catch (_) {} }));
    // nodes
    const ng = el('g', { class: 'nodes' }); svg.appendChild(ng);
    nodes.forEach((n) => {
      const x = cx(n), y = cy(n), st = n.status || 'same';
      const g = el('g', { class: `node ${n.type || 'process'} ${st}`, 'data-id': n.id, tabindex: 0, role: 'button' });
      const stroke = COLORS[st] || COLORS.same;
      if (n.type === 'decision') {
        const w = nodeW / 2 + 6, h = nodeH / 2 + 10;
        g.appendChild(el('polygon', { points: `${x},${y - h} ${x + w},${y} ${x},${y + h} ${x - w},${y}`, fill: 'var(--panel)', stroke, 'stroke-width': st === 'same' ? 1.25 : 2 }));
      } else if (n.type === 'terminal') {
        g.appendChild(el('rect', { x: x - nodeW / 2, y: y - nodeH / 2, width: nodeW, height: nodeH, rx: nodeH / 2, fill: st === 'same' ? 'var(--panel)' : 'var(--node-fill)', stroke, 'stroke-width': st === 'same' ? 1.25 : 2 }));
      } else if (n.type === 'note') {
        g.appendChild(el('rect', { x: x - nodeW / 2, y: y - nodeH / 2, width: nodeW, height: nodeH, rx: 4, fill: 'var(--code-bg)', stroke: 'var(--line)', 'stroke-dasharray': '3 3' }));
      } else {
        g.appendChild(el('rect', { x: x - nodeW / 2, y: y - nodeH / 2, width: nodeW, height: nodeH, rx: 6, fill: 'var(--panel)', stroke, 'stroke-width': st === 'same' ? 1.25 : 2 }));
        if (st !== 'same') g.appendChild(el('rect', { x: x - nodeW / 2, y: y - nodeH / 2, width: 5, height: nodeH, rx: 2, fill: stroke }));
      }
      if (st === 'removed') g.setAttribute('opacity', '.55');
      if (n.dim) g.setAttribute('opacity', '.32');
      const lines = String(n.label).split('\n');
      const t = el('text', { x, y: y - (lines.length - 1) * 7, 'text-anchor': 'middle', 'dominant-baseline': 'middle', class: 'node-label' + (n.mono ? ' mono' : '') });
      lines.forEach((ln, i) => t.appendChild(el('tspan', { x, dy: i === 0 ? 0 : 14 }, ln)));
      g.appendChild(t);
      if (n.badge) { const bx = x + nodeW / 2 - 6, by = y - nodeH / 2 + 6; g.appendChild(el('circle', { cx: bx, cy: by, r: 8, fill: n.badge === '✓' ? 'var(--ok)' : n.badge === '!' ? 'var(--warn)' : 'var(--bad)' })); g.appendChild(el('text', { x: bx, y: by + 0.5, 'text-anchor': 'middle', 'dominant-baseline': 'middle', class: 'badge' }, n.badge)); }
      if (n.detail || n.href) { const title = el('title'); title.textContent = (n.detail || '') + (n.href ? '\nClick for code' : ''); g.appendChild(title); }
      const act = () => { if (onSelect) onSelect({ kind: 'node', ...n }); else if (n.href) window.open(n.href, '_blank', 'noopener'); };
      g.addEventListener('click', act); g.addEventListener('keydown', (ev) => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); act(); } });
      ng.appendChild(g);
    });
    return { W, H };
  }
  return { render, COLORS };
})();
