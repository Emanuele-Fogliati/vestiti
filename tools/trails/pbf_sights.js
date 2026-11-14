#!/usr/bin/env node
// Famous sights of an OpenStreetMap country extract (ODbL), for the city walks.
//
//   node tools/trails/pbf_sights.js <country.osm.pbf> <out.json>
//
// No dependencies (same PBF reader as pbf_paths.js). A sight is a named node or way with a
// Wikidata id and a sight tag (historic, tourism attraction/museum/viewpoint, place of worship,
// temple/shrine/church building, park or garden, tower, market, square); ways take their first node.
'use strict';
const fs = require('fs');
const zlib = require('zlib');
const [, , PBF, OUT] = process.argv;
if (!PBF || !OUT) { console.error('usage: pbf_sights.js <pbf> <out.json>'); process.exit(2); }

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

// ---------- sights ----------
// A sight: named, with a Wikidata id (the fame signal), and a sight tag.
const HIST_SKIP = new Set(['memorial', 'wayside_cross', 'wayside_shrine', 'boundary_stone', 'milestone', 'tomb', 'grave', 'yes']);
const TOUR = new Set(['attraction', 'museum', 'viewpoint', 'gallery', 'zoo', 'aquarium', 'theme_park']);
const BLD = new Set(['temple', 'shrine', 'church', 'cathedral', 'chapel', 'mosque', 'pagoda', 'castle', 'palace', 'tower']);
function sightKind(t) {
  if (!t.name || !t.wikidata) return null;
  if (t.historic && !HIST_SKIP.has(t.historic)) return t.historic;
  if (TOUR.has(t.tourism)) return t.tourism;
  if (t.amenity === 'place_of_worship') return 'worship';
  if (BLD.has(t.building)) return t.building;
  if (t.leisure === 'park' || t.leisure === 'garden') return t.leisure;
  if (t.man_made === 'tower' || t.man_made === 'lighthouse') return t.man_made;
  if (t.amenity === 'marketplace' || t.amenity === 'theatre') return t.amenity;
  if (t.place === 'square' || t.highway === 'pedestrian') return 'square';
  return null;
}
const sights = []; // {kind, name, en, wiki, lat, lon, osm}
const wayFirst = new Map(); // first node id -> [sight index]
const nodeBlobs = [];
function sight(t, osm) {
  const k = sightKind(t); if (!k) return -1;
  sights.push({ kind: k, name: t.name, en: t['name:en'] || '', wiki: t.wikidata, lat: null, lon: null, osm });
  return sights.length - 1;
}
function ways(bk, g) {
  P = g.s; const end = g.e;
  while (P < end) {
    varint(); const l = varint(), we = P + l;
    let id = 0, first = null; const keys = [], vals = [];
    while (P < we) {
      const k2 = varint(), f = k2 >> 3, wt = k2 & 7;
      if (f === 1) id = varint();
      else if (f === 2) packed(v => keys.push(v));
      else if (f === 3) packed(v => vals.push(v));
      else if (f === 8) { let r = 0, n = 0; packed(v => { r += zz(v); if (n++ === 0) first = r; }); }
      else skip(wt);
    }
    if (!keys.length || first === null) continue;
    const t = {};
    for (let i = 0; i < keys.length; i++) t[bk.strings[keys[i]]] = bk.strings[vals[i]];
    const i = sight(t, 'w' + id);
    if (i >= 0) { if (!wayFirst.has(first)) wayFirst.set(first, []); wayFirst.get(first).push(i); }
  }
}
blobs((type, off, len) => {
  if (type !== 'OSMData') return;
  const bk = block(inflate(off, len));
  for (const g of bk.groups) {
    if (g.f === 2 || g.f === 1) { nodeBlobs.push([off, len]); break; }
    if (g.f === 3) ways(bk, g);
  }
});
console.error(`way sights ${sights.length}`);
function onNode(id, la, lo, t) {
  const w = wayFirst.get(id);
  if (w) for (const i of w) { sights[i].lat = +la.toFixed(6); sights[i].lon = +lo.toFixed(6); }
  if (t) { const i = sight(t, 'n' + id); if (i >= 0) { sights[i].lat = +la.toFixed(6); sights[i].lon = +lo.toFixed(6); } }
}
for (const [off, len] of nodeBlobs) {
  const bk = block(inflate(off, len));
  const s = bk.strings, g9 = 1e-9 * bk.gran;
  for (const g of bk.groups) {
    P = g.s;
    if (g.f === 2) {
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
        let t = null;
        if (kv && kv[q] !== 0) { t = {}; while (kv[q] !== 0) { t[s[kv[q]]] = s[kv[q + 1]]; q += 2; } q++; }
        else if (kv) q++;
        onNode(ids[i], la, lo, t);
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
        const t = {}; for (let i = 0; i < keys.length; i++) t[s[keys[i]]] = s[vals[i]];
        onNode(id, 1e-9 * (bk.latOff + bk.gran * la), 1e-9 * (bk.lonOff + bk.gran * lo), keys.length ? t : null);
      }
    }
  }
}
const out = sights.filter(x => x.lat !== null);
console.error(`sights ${out.length}`);
fs.writeFileSync(OUT, JSON.stringify({ source: PBF.split('/').pop(), sights: out }));
