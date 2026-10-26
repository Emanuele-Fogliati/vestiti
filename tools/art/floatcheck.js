// Physics check: finds big solid shapes with sky visible underneath them ("floating").
// usage: node tools/art/floatcheck.js <dir with <id>.svg + <id>.palette.json | palettes.json> [ids...]
// Needs Node and Playwright with Chromium (require('playwright') must resolve). Exit code 1 if any
// scene floats. It catches sky under a big solid shape (>= 20 x 30 px at 300 x 200), not
// everything in docs/LANDMARK_STYLE.md section 4b: reviewers still check the rest by eye.
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const DIR = process.argv[2]; const want = process.argv.slice(3);
const BASE = { sky: '#D6EAF5', far: '#A9C49A', mid: '#A88766', ice: '#FFFFFF', water: '#3F8FC4', near: '#22303C', sun: '#F6C431', leaf: '#5E8A4A', acc: '#C8463A', obj: '#C8463A' };
const all = fs.existsSync(path.join(DIR, 'palettes.json')) ? JSON.parse(fs.readFileSync(path.join(DIR, 'palettes.json'))) : {};
const pal = (id) => ({ ...BASE, ...(all[id] || {}), ...(fs.existsSync(path.join(DIR, id + '.palette.json')) ? JSON.parse(fs.readFileSync(path.join(DIR, id + '.palette.json'))) : {}) });
const ids = (want.length ? want : fs.readdirSync(DIR).filter((f) => f.endsWith('.svg')).map((f) => f.slice(0, -4))).sort();
(async () => {
  const b = await chromium.launch(); const p = await b.newPage();
  let bad = 0;
  for (const id of ids) {
    const pl = pal(id); const vars = Object.entries(pl).map(([k, v]) => `--il-${k}:${v}`).join(';');
    // sky drawn in a unique key colour so it can be told apart from other shapes
    const frag = fs.readFileSync(path.join(DIR, id + '.svg'), 'utf8');
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 200" width="600" height="400" style="${vars};--il-sky:#FF00FF" shape-rendering="crispEdges">${frag}</svg>`;
    const res = await p.evaluate(async (svg) => {
      const img = new Image(); img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svg)));
      await img.decode(); const c = document.createElement('canvas'); c.width = 600; c.height = 400;
      const x = c.getContext('2d'); x.drawImage(img, 0, 0); const d = x.getImageData(0, 0, 600, 400).data;
      const sky = (i) => d[i] > 230 && d[i + 1] < 40 && d[i + 2] > 230;
      const marks = [];
      for (let cx = 0; cx < 600; cx += 2) {
        let y = 0, hit = null;
        while (y < 400 && sky((y * 600 + cx) * 4)) y++;          // top sky
        while (y < 400 && !hit) {
          const s = y; while (y < 400 && !sky((y * 600 + cx) * 4)) y++;   // solid run
          const solid = y - s; const g0 = y; while (y < 400 && sky((y * 600 + cx) * 4)) y++;
          const gap = y - g0;
          if (solid >= 40 && gap >= 6 && y < 400) hit = { x: cx / 2, y: g0 / 2, gap: gap / 2 };
          else if (solid >= 40 && gap >= 6 && y >= 400) hit = { x: cx / 2, y: g0 / 2, gap: gap / 2, open: true };
        }
        if (hit) marks.push(hit);
      }
      const groups = [];
      for (const m of marks) {
        const g = groups[groups.length - 1];
        if (g && m.x - g.x1 <= 2 && Math.abs(m.y - g.y) < 12) { g.x1 = m.x; g.n++; } else groups.push({ x0: m.x, x1: m.x, y: m.y, n: 1 });
      }
      return groups.filter((g) => g.x1 - g.x0 >= 30);
    }, svg);
    if (res.length) { bad++; console.log('FLOAT', id, res.map((g) => `x ${g.x0}-${g.x1} gap below y ${g.y}`).join('; ')); }
    else console.log('ok   ', id);
  }
  await b.close(); process.exit(bad ? 1 : 0);
})();
