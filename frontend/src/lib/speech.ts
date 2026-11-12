/* Speak your trip (Manu, 2026-11-12). The browser's own speech recognition: Chrome, Edge and
   Safari have it (the audio goes to Google or Apple to be written down); Firefox does not, and
   the button is not shown there. */
import { useCallback, useEffect, useRef, useState } from "react";

type Rec = {
  lang: string; interimResults: boolean; continuous: boolean; maxAlternatives: number;
  start: () => void; stop: () => void; abort: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void) | null;
  onend: (() => void) | null; onerror: ((e: { error: string }) => void) | null;
};

function ctor(): (new () => Rec) | null {
  const w = window as unknown as { SpeechRecognition?: new () => Rec; webkitSpeechRecognition?: new () => Rec };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export function speechSupported(): boolean {
  return typeof window !== "undefined" && !!ctor();
}

/** Listen once: interim words while you speak, then onDone with the whole sentence. */
export function useSpeech(onDone: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const [heard, setHeard] = useState("");
  const [error, setError] = useState("");
  const rec = useRef<Rec | null>(null);
  const finalText = useRef("");
  const done = useRef(onDone);
  done.current = onDone;

  useEffect(() => () => rec.current?.abort(), []);

  const start = useCallback(() => {
    const C = ctor();
    if (!C) { setError("Your browser can't listen. Try Chrome, Edge or Safari, or type it."); return; }
    rec.current?.abort();
    const r = new C();
    r.lang = navigator.language || "en-US";
    r.interimResults = true;
    r.continuous = true;
    r.maxAlternatives = 1;
    finalText.current = "";
    setHeard(""); setError("");
    r.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) finalText.current += res[0].transcript + " ";
        else interim += res[0].transcript;
      }
      setHeard((finalText.current + interim).trim());
    };
    r.onerror = (e) => {
      setError(e.error === "not-allowed" || e.error === "service-not-allowed"
        ? "The microphone is blocked: allow it in the browser's address bar, or type it."
        : e.error === "no-speech" ? "I didn't hear anything. Try again, a bit closer." : "Listening stopped. Try again or type it.");
    };
    r.onend = () => {
      setListening(false);
      const t = finalText.current.trim();
      if (t) done.current(t);
    };
    rec.current = r;
    setListening(true);
    r.start();
  }, []);

  const stop = useCallback(() => rec.current?.stop(), []);
  return { listening, heard, error, start, stop, supported: speechSupported() };
}
