// Side-by-side review: the reference photo (left) next to the scene as the app shows it (right), same size.
// usage: node tools/art/compare.js <dir with <id>.svg + <id>.palette.json> [refs dir] [ids...]
// refs dir defaults to <dir>/refs (made by tools/art/ref.py). Writes <dir>/compare/<id>.png.
// Reviewers open these PNGs and check viewpoint, proportions and signature features against the photo
// (docs/LANDMARK_STYLE.md section 0). Needs Node + Playwright, and python3 for app.art.render.
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
const { execFileSync } = require('child_process');
const DIR = path.resolve(process.argv[2]);
const REFS = path.resolve(process.argv[3] && fs.existsSync(process.argv[3]) && fs.statSync(process.argv[3]).isDirectory() ? process.argv[3] : path.join(DIR, 'refs'));
const want = process.argv.slice(fs.existsSync(process.argv[3] || '') ? 4 : 3);
const BACKEND = path.join(__dirname, '..', '..', 'backend');
const ids = (want.length ? want : fs.readdirSync(DIR).filter((f) => f.endsWith('.svg')).map((f) => f.slice(0, -4))).sort();
(async () => {
  const out = path.join(DIR, 'compare'); fs.mkdirSync(out, { recursive: true });
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1220, height: 440 } });
  for (const id of ids) {
    const scene = execFileSync('python3', ['-m', 'app.art.render', path.join(DIR, id + '.svg')], { cwd: BACKEND, encoding: 'utf8' });
    const ref = ['.jpg', '.jpeg', '.png', '.webp'].map((e) => path.join(REFS, id + e)).find((f) => fs.existsSync(f));
    const img = ref ? `<img src="data:image/${path.extname(ref).slice(1).replace('jpg', 'jpeg')};base64,${fs.readFileSync(ref).toString('base64')}" style="width:600px;height:400px;object-fit:cover">`
      : '<div style="width:600px;height:400px;background:#eee;display:flex;align-items:center;justify-content:center">no reference photo</div>';
    await p.setContent(`<body style="margin:0;font:14px sans-serif;background:#fff"><div style="padding:4px 10px">${id}: reference | scene</div><div style="display:flex;gap:10px;padding:0 5px">${img}${scene}</div></body>`);
    await p.screenshot({ path: path.join(out, id + '.png') });
    console.log(path.join(out, id + '.png'));
  }
  await b.close();
})();
