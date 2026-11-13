// Landmark scenes (Machu Picchu, Cusco cathedral...) come from the API as SVG fragments drawn
// with the --il-* tokens. Each one is fetched once per page load and shared by every card.
//
// Never fire them all at once: the home globe has ~2,600 scenes and a browser refuses most of a
// burst that size (Chrome: net::ERR_INSUFFICIENT_RESOURCES). The refused ones used to be remembered
// as "no picture" for the whole visit, so a place card showed the generic scene instead of its own
// drawing (Gardskagi Lighthouse, 2026-11-12). Now at most MAX_PARALLEL requests run, a picture the
// person is looking at jumps the queue, and a failed request is retried and never remembered.

export const MAX_PARALLEL = 6;
const RETRIES = 2;

/** null = the server has no such scene (404); undefined = it could not be fetched now. */
type Result = string | null | undefined;
interface Job { id: string; urgent: boolean; done: (r: Result) => void }

const cache = new Map<string, Promise<string | null>>();
const queue: Job[] = [];
let running = 0;

let fetchScene = async (id: string): Promise<Result> => {
  for (let attempt = 0; ; attempt++) {
    try {
      const r = await fetch(`/api/art/landmarks/${encodeURIComponent(id)}.svg?v=${__BUILD_ID__}`);
      if (r.ok) return await r.text();
      if (r.status === 404) return null;
    } catch { /* network refused or dropped: try again */ }
    if (attempt >= RETRIES) return undefined;
    await new Promise((ok) => setTimeout(ok, 400 * (attempt + 1)));
  }
};

function pump() {
  while (running < MAX_PARALLEL && queue.length) {
    const job = queue.shift()!;
    running++;
    fetchScene(job.id).then(job.done, () => job.done(undefined)).finally(() => { running--; pump(); });
  }
}

/** The scene, or null when there is none (or it can't be fetched right now: asking again retries).
 *  `urgent`: the person is looking at it (a place card, a stop), so it goes before the globe's
 *  thumbnails still waiting. */
export function loadLandmark(id: string, urgent = false): Promise<string | null> {
  const known = cache.get(id);
  if (known) {
    const at = urgent ? queue.findIndex((j) => j.id === id) : -1;
    if (at >= 0) queue[at].urgent = true;
    if (at > 0) queue.unshift(...queue.splice(at, 1));
    return known;
  }
  const p = new Promise<string | null>((resolve) => {
    const job: Job = {
      id,
      urgent,
      done: (r) => {
        if (r === undefined) cache.delete(id);  // not "no picture": the next card asks again
        resolve(r ?? null);
      },
    };
    if (urgent) queue.unshift(job); else queue.push(job);
  });
  cache.set(id, p);
  pump();
  return p;
}

/** The globe turned or zoomed away before this thumbnail's turn came: don't fetch it. Only a
 *  thumbnail still waiting is dropped (never one a card asked for); its promise never settles,
 *  and the next loadLandmark for it starts afresh. True when it was dropped. */
export function cancelLandmark(id: string): boolean {
  const at = queue.findIndex((j) => j.id === id && !j.urgent);
  if (at < 0) return false;
  queue.splice(at, 1);
  cache.delete(id);
  return true;
}

/** Tests only: swap the network call and forget everything. */
export function _resetForTests(fetcher?: (id: string) => Promise<Result>) {
  cache.clear();
  queue.length = 0;
  running = 0;
  if (fetcher) fetchScene = fetcher;
}

export function _inFlight() {
  return { running, queued: queue.length };
}
