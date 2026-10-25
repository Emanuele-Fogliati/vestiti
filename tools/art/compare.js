// Side-by-side review: the reference photos (left, up to 4) next to the scene as the app shows it (right).
// usage: node tools/art/compare.js <dir with <id>.svg + <id>.palette.json> [ids...]
// Photos come from <dir>/refs/<id>-1.jpg .. <id>-4.jpg (made by tools/art/ref.py). Writes <dir>/compare/<id>.png.
// Drawers and reviewers open these PNGs and check viewpoint, proportions and signature features against
// the photos (docs/LANDMARK_STYLE.md section 0). Needs Node + Playwright, and python3 for app.art.render.
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const { execFileSync } = require('child_process');
const DIR = path.resolve(process.argv[2]); const REFS = path.join(DIR, 'refs');
const want = process.argv.slice(3);
const BACKEND = path.join(__dirname, '..', '..', 'backend');
const ids = (want.length ? want : fs.readdirSync(DIR).filter((f) => f.endsWith('.svg')).map((f) => f.slice(0, -4))).sort();
const photo = (f) => `<img src="data:image/jpeg;base64,${fs.readFileSync(f).toString('base64')}" style="width:100%;height:100%;object-fit:cover;display:block">`;
(async () => {
  const out = path.join(DIR, 'compare'); fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1220, height: 440 } });
  for (const id of ids) {
    const scene = execFileSync('python3', ['-m', 'app.art.render', path.join(DIR, id + '.svg')], { cwd: BACKEND, encoding: 'utf8' });
    const refs = [1, 2, 3, 4].map((n) => path.join(REFS, `${id}-${n}.jpg`)).filter((f) => fs.existsSync(f));
    const cells = refs.length === 1 ? 1 : 2;
    const left = refs.length
      ? `<div style="width:600px;height:400px;display:grid;gap:4px;grid-template-columns:repeat(${cells},1fr);grid-template-rows:repeat(${refs.length > 2 ? 2 : 1},1fr)">${refs.map(photo).join('')}</div>`
      : '<div style="width:600px;height:400px;background:#eee;display:flex;align-items:center;justify-content:center">no reference photo</div>';
    await p.setContent(`<body style="margin:0;font:14px sans-serif;background:#fff"><div style="padding:4px 10px">${id}: ${refs.length} reference photo(s) | scene</div><div style="display:flex;gap:10px;padding:0 5px">${left}${scene}</div></body>`);
    await p.screenshot({ path: path.join(out, id + '.png') });
    console.log(path.join(out, id + '.png'));
  }
  await b.close();
})();
