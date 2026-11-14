#!/usr/bin/env node
// Walks to named mountain goals from an OpenStreetMap country extract (ODbL).
//
//   node tools/trails/pbf_paths.js <country.osm.pbf> <out.json>
//
// No dependencies: reads the PBF format directly (zlib blobs only).
// Goals: named peaks/volcanoes, saddles, huts, waterfalls, viewpoints (nodes) and named lakes (ways).
// For each goal it finds the shortest walk on footpaths (path, footway, steps, bridleway)
// to the nearest point where that network touches a road, and writes the line (goal first).
'use strict';
const fs = require('fs');
const zlib = require('zlib');

const [, , PBF, OUT] = process.argv;
if (!PBF || !OUT) { console.error('usage: pbf_paths.js <pbf> <out.json>'); process.exit(2); }
const MAX_KM = +(process.env.MAX_KM || 25);
const SNAP_M = 250;

// ---------- protobuf helpers ----------
let B, P, E;
function varint() {
  let r = 0, m = 1, b;
  do { b = B[P++]; r += (b & 0x7f) * m; m *= 128; } while (b & 0x80);
  return r;
}
function zz(v) { return v % 2 === 1 ? -(v + 1) / 2 : v / 2; }
function skip(wt) {
  if (wt === 0) varint();
  else if (wt === 2) { const l = varint(); P += l; }
  else if (wt === 1) P += 8;
  else if (wt === 5) P += 4;
  else throw new Error('wire type ' + wt);
}
function packed(fn) { // calls fn(value) for each packed varint
  const l = varint(), end = P + l;
  while (P < end) fn(varint());
}

// ---------- blob reading ----------
const fd = fs.openSync(PBF, 'r');
const size = fs.fstatSync(fd).size;
function readAt(pos, n) { const b = Buffer.allocUnsafe(n); fs.readSync(fd, b, 0, n, pos); return b; }
function blobs(cb) { // cb(type, offset, length)
  let pos = 0;
  while (pos < size) {
    const hl = readAt(pos, 4).readUInt32BE(0); pos += 4;
    B = readAt(pos, hl); P = 0; E = hl; pos += hl;
    let type = '', ds = 0;
    while (P < E) {
      const k = varint(), f = k >> 3, wt = k & 7;
      if (f === 1) { const l = varint(); type = B.toString('utf8', P, P + l); P += l; }
      else if (f === 3) ds = varint();
      else skip(wt);
    }
    cb(type, pos, ds); pos += ds;
  }
}
function inflate(off, len) {
  B = readAt(off, len); P = 0;
  let raw = null, z = null;
  while (P < len) {
    const k = varint(), f = k >> 3, wt = k & 7;
    if (f === 1) { const l = varint(); raw = B.subarray(P, P + l); P += l; }
    else if (f === 3) { const l = varint(); z = B.subarray(P, P + l); P += l; }
    else if (wt === 2 && f > 3) throw new Error('unsupported blob compression ' + f);
    else skip(wt);
  }
  return raw || zlib.inflateSync(z);
}

// primitive block: returns {strings, gran, latOff, lonOff, groups:[{f, s, e}]} and leaves B = block
function block(buf) {
  B = buf; P = 0; E = buf.length;
  const strings = []; const groups = []; let gran = 100, latOff = 0, lonOff = 0;
  while (P < E) {
    const k = varint(), f = k >> 3, wt = k & 7;
    if (f === 1) {
      const l = varint(), end = P + l;
      while (P < end) { varint(); const sl = varint(); strings.push(B.toString('utf8', P, P + sl)); P += sl; }
    } else if (f === 2) {
      const l = varint(), s0 = P; const kind = varint() >> 3;
      groups.push({ f: kind, s: s0, e: s0 + l }); P = s0 + l;
    } else if (f === 17) gran = varint();
    else if (f === 19) latOff = zz(varint());
    else if (f === 20) lonOff = zz(varint());
    else skip(wt);
  }
  return { strings, gran, latOff, lonOff, groups };
}

// ---------- growable typed arrays ----------
class Grow {
  constructor(T, n = 1 << 20) { this.T = T; this.a = new T(n); this.n = 0; }
  push(v) { if (this.n === this.a.length) { const b = new this.T(this.a.length * 2); b.set(this.a); this.a = b; } this.a[this.n++] = v; }
  done() { return this.a.subarray(0, this.n); }
}

// ---------- pass 1: ways ----------
const ROAD = new Set(['motorway', 'trunk', 'primary', 'secondary', 'tertiary', 'unclassified', 'residential',
  'service', 'living_street', 'motorway_link', 'trunk_link', 'primary_link', 'secondary_link', 'tertiary_link', 'road']);
const WALK = new Set(['path', 'footway', 'steps', 'bridleway']); // tracks are drivable (4x4 roads in the highlands): they count as roads
const walkRefs = new Grow(Float64Array, 1 << 22), walkStart = new Grow(Uint32Array), walkName = new Grow(Int32Array);
const walkSac = new Grow(Uint8Array);
const roadRefs = new Grow(Float64Array, 1 << 22);
const lakeRefs = new Grow(Float64Array), lakeStart = new Grow(Uint32Array);
const lakes = []; // {name, en, id}
const names = []; const nameIx = new Map();
function nameId(s) { if (!s) return -1; let i = nameIx.get(s); if (i === undefined) { i = names.length; names.push(s); nameIx.set(s, i); } return i; }
const SAC = { hiking: 1, mountain_hiking: 2, demanding_mountain_hiking: 3, alpine_hiking: 4, demanding_alpine_hiking: 5, difficult_alpine_hiking: 6 };
const nodeBlobs = [];
let nWays = 0;

function ways(bk, g) {
  P = g.s; const end = g.e;
  while (P < end) {
    const k = varint(); // field 3 = Way
    const l = varint(), we = P + l;
    let id = 0; const keys = [], vals = [], refs = [];
    while (P < we) {
      const k2 = varint(), f = k2 >> 3, wt = k2 & 7;
      if (f === 1) id = varint();
      else if (f === 2) packed(v => keys.push(v));
      else if (f === 3) packed(v => vals.push(v));
      else if (f === 8) { let r = 0; packed(v => { r += zz(v); refs.push(r); }); }
      else skip(wt);
    }
    nWays++;
    const t = {};
    for (let i = 0; i < keys.length; i++) t[bk.strings[keys[i]]] = bk.strings[vals[i]];
    const hw = t.highway;
    if (hw) {
      const acc = t.foot || t.access;
      const isWalk = WALK.has(hw) &&
        acc !== 'private' && acc !== 'no' && t.footway !== 'sidewalk' && t.footway !== 'crossing' && t.area !== 'yes';
      if (isWalk) {
        walkStart.push(walkRefs.n);
        for (const r of refs) walkRefs.push(r);
        walkName.push(nameId(t['name:en'] || t.name || ''));
        walkSac.push(SAC[t.sac_scale] || 0);
      } else if (ROAD.has(hw) || hw === 'track') {
        for (const r of refs) roadRefs.push(r);
      }
    } else if (t.natural === 'water' && t.name && (!t.water || t.water === 'lake' || t.water === 'reservoir' || t.water === 'pond') && refs.length > 3) {
      lakes.push({ name: t.name, en: t['name:en'] || t['int_name'] || '', id, kind: t.water || 'lake' });
      lakeStart.push(lakeRefs.n);
      for (const r of refs) lakeRefs.push(r);
    }
  }
}

console.error('pass 1 (ways)...');
let t0 = Date.now();
blobs((type, off, len) => {
  if (type !== 'OSMData') return;
  const bk = block(inflate(off, len));
  for (const g of bk.groups) {
    if (g.f === 2 || g.f === 1) { nodeBlobs.push([off, len]); break; }
    if (g.f === 3) ways(bk, g);
  }
});
walkStart.push(walkRefs.n); lakeStart.push(lakeRefs.n);
console.error(`  ${nWays} ways, walk ways ${walkName.n}, walk refs ${walkRefs.n}, road refs ${roadRefs.n}, lakes ${lakes.length}, ${(Date.now() - t0) / 1000}s`);

// unique sorted ids of walk nodes; lake nodes need coords too
function uniq(a) { a.sort(); let n = 0; for (let i = 0; i < a.length; i++) if (i === 0 || a[i] !== a[i - 1]) a[n++] = a[i]; return a.subarray(0, n); }
const WR = walkRefs.done(), RR = roadRefs.done(), LR = lakeRefs.done();
const U = uniq(Float64Array.from(WR));
const L = uniq(Float64Array.from(LR));
function find(a, id) { let lo = 0, hi = a.length - 1; while (lo <= hi) { const m = (lo + hi) >> 1; const v = a[m]; if (v === id) return m; if (v < id) lo = m + 1; else hi = m - 1; } return -1; }
const N = U.length;
const access = new Uint8Array(N);
{ const R = uniq(RR); let i = 0, j = 0; while (i < N && j < R.length) { if (U[i] === R[j]) { access[i] = 1; i++; j++; } else if (U[i] < R[j]) i++; else j++; } }
console.error(`  walk nodes ${N}, access nodes ${access.reduce((s, v) => s + v, 0)}`);

// ---------- pass 2: nodes ----------
const lat = new Float64Array(N).fill(NaN), lon = new Float64Array(N).fill(NaN);
const llat = new Float64Array(L.length).fill(NaN), llon = new Float64Array(L.length).fill(NaN);
const goals = []; // {kind, name, en, ele, lat, lon, id}
function goalKind(t) {
  if (!t.name) return null;
  if (t.natural === 'peak' || t.natural === 'volcano') return 'peak';
  if (t.natural === 'saddle' || t.mountain_pass === 'yes') return 'pass';
  if (t.tourism === 'alpine_hut' || t.tourism === 'wilderness_hut') return 'hut';
  if (t.waterway === 'waterfall' || t.natural === 'waterfall') return 'waterfall';
  if (t.tourism === 'viewpoint') return 'viewpoint';
  if (t.natural === 'glacier') return 'glacier';
  return null;
}
function addGoal(t, id, la, lo) {
  const k = goalKind(t); if (!k) return;
  goals.push({ kind: k, name: t.name, en: t['name:en'] || t.int_name || t['name:ja-Latn'] || t['name:ja_rm'] || t['name:vi-Latn'] || '',
    ele: parseFloat(t.ele) || null, lat: +la.toFixed(6), lon: +lo.toFixed(6), id, wiki: t.wikidata || '' });
}
let ui = 0, li = 0, lastId = -1;
function setNode(id, la, lo) {
  if (id < lastId) { ui = 0; li = 0; } lastId = id; // unsorted file: restart merge
  while (ui < N && U[ui] < id) ui++;
  if (ui < N && U[ui] === id) { lat[ui] = la; lon[ui] = lo; }
  while (li < L.length && L[li] < id) li++;
  if (li < L.length && L[li] === id) { llat[li] = la; llon[li] = lo; }
}
console.error('pass 2 (nodes)...'); t0 = Date.now();
for (const [off, len] of nodeBlobs) {
  const bk = block(inflate(off, len));
  const s = bk.strings, g9 = 1e-9 * bk.gran;
  for (const g of bk.groups) {
    P = g.s;
    if (g.f === 2) {
      // DenseNodes
      varint(); const l = varint(); const end = P + l;
      let ids = null, lats = null, lons = null, kv = null;
      while (P < end) {
        const k = varint(), f = k >> 3, wt = k & 7;
        if (f === 1) { ids = []; let r = 0; packed(v => { r += zz(v); ids.push(r); }); }
        else if (f === 8) { lats = []; let r = 0; packed(v => { r += zz(v); lats.push(r); }); }
        else if (f === 9) { lons = []; let r = 0; packed(v => { r += zz(v); lons.push(r); }); }
        else if (f === 10) { kv = []; packed(v => kv.push(v)); }
        else skip(wt);
      }
      let q = 0;
      for (let i = 0; i < ids.length; i++) {
        const la = 1e-9 * bk.latOff + g9 * lats[i], lo = 1e-9 * bk.lonOff + g9 * lons[i];
        setNode(ids[i], la, lo);
        if (kv && kv[q] !== 0) {
          const t = {};
          while (kv[q] !== 0) { t[s[kv[q]]] = s[kv[q + 1]]; q += 2; }
          q++;
          addGoal(t, ids[i], la, lo);
        } else if (kv) q++;
      }
    } else if (g.f === 1) {
      const end = g.e;
      while (P < end) {
        varint(); const l = varint(), ne = P + l;
        let id = 0, la = 0, lo = 0; const keys = [], vals = [];
        while (P < ne) {
          const k = varint(), f = k >> 3, wt = k & 7;
          if (f === 1) id = zz(varint());
          else if (f === 2) packed(v => keys.push(v));
          else if (f === 3) packed(v => vals.push(v));
          else if (f === 8) la = zz(varint());
          else if (f === 9) lo = zz(varint());
          else skip(wt);
        }
        const LA = 1e-9 * (bk.latOff + bk.gran * la), LO = 1e-9 * (bk.lonOff + bk.gran * lo);
        setNode(id, LA, LO);
        const t = {}; for (let i = 0; i < keys.length; i++) t[s[keys[i]]] = s[vals[i]];
        addGoal(t, id, LA, LO);
      }
    }
  }
}
console.error(`  goals ${goals.length}, ${(Date.now() - t0) / 1000}s`);

// lakes as goals: every shore node is a possible arrival
for (let k = 0; k < lakes.length; k++) {
  const pts = [];
  for (let j = lakeStart.a[k]; j < lakeStart.a[k + 1]; j++) { const i = find(L, LR[j]); if (i >= 0 && !isNaN(llat[i])) pts.push([llat[i], llon[i]]); }
  if (pts.length < 3) continue;
  const la = pts.reduce((s, p) => s + p[0], 0) / pts.length, lo = pts.reduce((s, p) => s + p[1], 0) / pts.length;
  goals.push({ kind: 'lake', name: lakes[k].name, en: lakes[k].en, ele: null, lat: +la.toFixed(6), lon: +lo.toFixed(6), id: lakes[k].id, shore: pts });
}

// ---------- graph ----------
console.error('graph...'); t0 = Date.now();
const R = 6371.0088, rad = Math.PI / 180;
function km(a1, o1, a2, o2) {
  const dl = (a2 - a1) * rad, dn = (o2 - o1) * rad;
  const h = Math.sin(dl / 2) ** 2 + Math.cos(a1 * rad) * Math.cos(a2 * rad) * Math.sin(dn / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}
const W = walkName.n, WS = walkStart.done(), WN = walkName.done(), WSAC = walkSac.done();
const ix = new Int32Array(WR.length); for (let j = 0; j < WR.length; j++) ix[j] = find(U, WR[j]);
const deg = new Uint32Array(N + 1);
for (let w = 0; w < W; w++) for (let j = WS[w]; j < WS[w + 1] - 1; j++) { deg[ix[j]]++; deg[ix[j + 1]]++; }
const off = new Uint32Array(N + 1); for (let i = 0; i < N; i++) off[i + 1] = off[i] + deg[i];
const adj = new Int32Array(off[N]), aw = new Float32Array(off[N]), away = new Int32Array(off[N]);
const fill = off.slice(0, N);
for (let w = 0; w < W; w++) for (let j = WS[w]; j < WS[w + 1] - 1; j++) {
  const a = ix[j], b = ix[j + 1]; if (a < 0 || b < 0 || isNaN(lat[a]) || isNaN(lat[b])) continue;
  const d = km(lat[a], lon[a], lat[b], lon[b]);
  adj[fill[a]] = b; aw[fill[a]] = d; away[fill[a]++] = w;
  adj[fill[b]] = a; aw[fill[b]] = d; away[fill[b]++] = w;
}
// spatial grid of walk nodes (cells of 0.01 deg)
let minLa = 90, minLo = 180; for (let i = 0; i < N; i++) if (!isNaN(lat[i])) { if (lat[i] < minLa) minLa = lat[i]; if (lon[i] < minLo) minLo = lon[i]; }
const cell = (la, lo) => Math.floor((la - minLa) * 100) * 100000 + Math.floor((lo - minLo) * 100);
const grid = new Map();
for (let i = 0; i < N; i++) { if (isNaN(lat[i]) || deg[i] === 0) continue; const c = cell(lat[i], lon[i]); let a = grid.get(c); if (!a) grid.set(c, a = []); a.push(i); }
function near(la, lo, m) { // walk nodes within m metres
  const out = [];
  const c0 = Math.floor((la - minLa) * 100), c1 = Math.floor((lo - minLo) * 100);
  for (let a = c0 - 1; a <= c0 + 1; a++) for (let b = c1 - 1; b <= c1 + 1; b++) {
    const arr = grid.get(a * 100000 + b); if (!arr) continue;
    for (const i of arr) { const d = km(la, lo, lat[i], lon[i]) * 1000; if (d <= m) out.push([i, d]); }
  }
  return out;
}
console.error(`  edges ${off[N] / 2}, cells ${grid.size}, ${(Date.now() - t0) / 1000}s`);

// ---------- shortest walk from each goal to the road network ----------
const dist = new Float64Array(N).fill(Infinity), prev = new Int32Array(N).fill(-1), pway = new Int32Array(N).fill(-1);
const touched = [];
let heap = [];
function hpush(d, i) { heap.push([d, i]); let k = heap.length - 1; while (k > 0) { const p = (k - 1) >> 1; if (heap[p][0] <= heap[k][0]) break; [heap[p], heap[k]] = [heap[k], heap[p]]; k = p; } }
function hpop() { const top = heap[0], last = heap.pop(); if (heap.length) { heap[0] = last; let k = 0; for (;;) { const l = 2 * k + 1, r = l + 1; let m = k; if (l < heap.length && heap[l][0] < heap[m][0]) m = l; if (r < heap.length && heap[r][0] < heap[m][0]) m = r; if (m === k) break; [heap[m], heap[k]] = [heap[k], heap[m]]; k = m; } } return top; }
function walkTo(sources) {
  for (const i of touched) { dist[i] = Infinity; prev[i] = -1; pway[i] = -1; } touched.length = 0; heap = [];
  for (const [i, d0] of sources) if (d0 < dist[i]) { dist[i] = d0; touched.push(i); hpush(d0, i); }
  while (heap.length) {
    const [d, i] = hpop(); if (d > dist[i]) continue;
    if (access[i]) return i;
    if (d > MAX_KM) return -1;
    for (let e = off[i]; e < off[i + 1]; e++) {
      const j = adj[e], nd = d + aw[e];
      if (nd < dist[j]) { if (dist[j] === Infinity) touched.push(j); dist[j] = nd; prev[j] = i; pway[j] = away[e]; hpush(nd, j); }
    }
  }
  return -1;
}
const out = [];
let noPath = 0, noRoad = 0; t0 = Date.now();
for (const g of goals) {
  let src = [];
  if (g.shore) { for (const [la, lo] of g.shore) for (const [i, d] of near(la, lo, 120)) src.push([i, d / 1000]); }
  else src = near(g.lat, g.lon, SNAP_M).map(([i, d]) => [i, d / 1000]);
  if (!src.length) { noPath++; continue; }
  const end = walkTo(src);
  if (end < 0) { noRoad++; continue; }
  const line = [], wayKm = new Map(); let sac = 0;
  for (let i = end; i >= 0; i = prev[i]) {
    line.push([+lat[i].toFixed(5), +lon[i].toFixed(5)]);
    if (pway[i] >= 0) { const w = pway[i]; sac = Math.max(sac, WSAC[w]); const n = WN[w]; if (n >= 0) wayKm.set(n, (wayKm.get(n) || 0) + dist[i] - dist[prev[i]]); }
  }
  line.reverse(); // goal first ... road last
  const via = [...wayKm.entries()].sort((a, b) => b[1] - a[1]).slice(0, 2).map(([n]) => names[n]);
  const rec = { kind: g.kind, id: g.id, name: g.name, en: g.en, ele: g.ele, wiki: g.wiki || '', lat: g.lat, lon: g.lon,
    km: +dist[end].toFixed(2), sac, via, line };
  out.push(rec);
}
console.error(`  walks ${out.length}, goals off the path network ${noPath}, no road within ${MAX_KM} km ${noRoad}, ${(Date.now() - t0) / 1000}s`);
fs.writeFileSync(OUT, JSON.stringify({ source: PBF.split('/').pop(), walks: out }));
