import { beforeEach, describe, expect, it } from "vitest";
import { MAX_PARALLEL, _inFlight, _resetForTests, cancelLandmark, loadLandmark } from "../landmarks";

/** A fake server: each request waits until the test answers it. */
function server() {
  const pending: { id: string; answer: (r: string | null | undefined) => void }[] = [];
  const calls: string[] = [];
  const fetcher = (id: string) => new Promise<string | null | undefined>((answer) => { calls.push(id); pending.push({ id, answer }); });
  return { pending, calls, fetcher };
}
const tick = () => new Promise((r) => setTimeout(r, 0));

describe("loadLandmark", () => {
  let srv: ReturnType<typeof server>;
  beforeEach(() => { srv = server(); _resetForTests(srv.fetcher); });

  it("never runs more than a few requests at once, however many are asked (the globe asks ~2,600)", async () => {
    for (let i = 0; i < 2600; i++) loadLandmark(`xx-${i}`);
    expect(_inFlight()).toEqual({ running: MAX_PARALLEL, queued: 2600 - MAX_PARALLEL });
    srv.pending.shift()!.answer("<svg/>");
    await tick();
    expect(_inFlight().running).toBe(MAX_PARALLEL);
    expect(srv.calls.length).toBe(MAX_PARALLEL + 1);
  });

  it("a picture someone is looking at goes before the globe's waiting thumbnails", async () => {
    for (let i = 0; i < 50; i++) loadLandmark(`xx-${i}`);
    const card = loadLandmark("is-gardskagi-lighthouse", true);
    const again = loadLandmark("xx-40", true);  // already queued: moves to the front
    srv.pending.shift()!.answer("a");
    srv.pending.shift()!.answer("b");
    await tick();
    expect(srv.calls.slice(MAX_PARALLEL, MAX_PARALLEL + 2)).toEqual(["xx-40", "is-gardskagi-lighthouse"]);
    void card; void again;
  });

  it("drops a globe thumbnail still waiting when the globe moved on, never one a card asked for", async () => {
    for (let i = 0; i < 10; i++) loadLandmark(`xx-${i}`);
    expect(cancelLandmark("xx-0")).toBe(false); // already being fetched
    expect(cancelLandmark("xx-8")).toBe(true);
    expect(_inFlight().queued).toBe(10 - MAX_PARALLEL - 1);
    loadLandmark("xx-9", true);
    expect(cancelLandmark("xx-9")).toBe(false);
    loadLandmark("xx-8"); // asked again: queued afresh
    expect(_inFlight().queued).toBe(10 - MAX_PARALLEL);
  });

  it("asks once per scene and shares the answer", async () => {
    const a = loadLandmark("pe-machu-picchu");
    const b = loadLandmark("pe-machu-picchu", true);
    expect(a).toBe(b);
    srv.pending[0].answer("<svg/>");
    expect(await a).toBe("<svg/>");
    expect(srv.calls).toEqual(["pe-machu-picchu"]);
  });

  it("a failed request is not remembered as 'no picture': the next card asks again", async () => {
    const first = loadLandmark("is-gardskagi-lighthouse");
    srv.pending[0].answer(undefined);
    expect(await first).toBeNull();
    const second = loadLandmark("is-gardskagi-lighthouse");
    await tick();
    srv.pending[1].answer("<svg/>");
    expect(await second).toBe("<svg/>");
  });

  it("a scene the server doesn't have (404) is remembered", async () => {
    const first = loadLandmark("xx-none");
    srv.pending[0].answer(null);
    expect(await first).toBeNull();
    expect(await loadLandmark("xx-none")).toBeNull();
    expect(srv.calls).toEqual(["xx-none"]);
  });
});
