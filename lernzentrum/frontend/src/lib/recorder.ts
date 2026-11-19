// Live recorder for iPad Safari and desktop browsers.
// - MediaRecorder is restarted every SEGMENT_MS so each chunk is a standalone file (webm/opus or mp4/aac on iPad).
// - Chunks are uploaded immediately; if the network is down they go to IndexedDB and are uploaded later
//   (marked "late" → the server transcribes them afterwards and marks the gap).
// - Screen Wake Lock keeps the iPad awake; Safari cannot record in the background, so we warn on visibility loss.

const SEGMENT_MS = 8000;
const DB_NAME = "lernzentrum";
const STORE = "chunks";

export interface QueuedChunk {
  key: string;
  recId: number;
  seq: number;
  offset_s: number;
  duration_s: number;
  mime: string;
  blob: Blob;
}

export interface RecorderState {
  recording: boolean;
  online: boolean;
  queued: number;
  uploaded: number;
  level: number;
  hidden: boolean;
  wakeLock: boolean;
  error: string | null;
  elapsed: number;
}

function idb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "key" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function idbPut(c: QueuedChunk) {
  const db = await idb();
  await new Promise<void>((res, rej) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(c);
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
  });
}

async function idbAll(): Promise<QueuedChunk[]> {
  const db = await idb();
  return new Promise((res, rej) => {
    const req = db.transaction(STORE).objectStore(STORE).getAll();
    req.onsuccess = () => res(req.result as QueuedChunk[]);
    req.onerror = () => rej(req.error);
  });
}

async function idbDel(key: string) {
  const db = await idb();
  await new Promise<void>((res) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(key);
    tx.oncomplete = () => res();
  });
}

export async function pendingChunks(recId?: number): Promise<number> {
  try {
    const all = await idbAll();
    return all.filter((c) => recId === undefined || c.recId === recId).length;
  } catch {
    return 0;
  }
}

function csrf(): string {
  const m = document.cookie.match(/(?:^|; )lz_csrf=([^;]+)/);
  return m ? decodeURIComponent(m[1]) : "";
}

async function uploadChunk(c: QueuedChunk, late: boolean): Promise<boolean> {
  const fd = new FormData();
  const ext = c.mime.includes("mp4") ? "mp4" : c.mime.includes("ogg") ? "ogg" : "webm";
  fd.append("file", c.blob, `chunk-${c.seq}.${ext}`);
  fd.append("seq", String(c.seq));
  fd.append("offset_s", String(c.offset_s));
  fd.append("duration_s", String(c.duration_s));
  fd.append("late", String(late));
  try {
    const res = await fetch(`/api/recordings/${c.recId}/chunks`, {
      method: "POST",
      body: fd,
      headers: { "x-csrf-token": csrf() },
      credentials: "same-origin",
    });
    return res.ok;
  } catch {
    return false;
  }
}

/** Upload chunks that were recorded while offline (also after an app restart). */
export async function flushQueue(onProgress?: (left: number) => void): Promise<number> {
  let all: QueuedChunk[] = [];
  try {
    all = await idbAll();
  } catch {
    return 0;
  }
  let done = 0;
  for (const c of all.sort((a, b) => a.seq - b.seq)) {
    if (!navigator.onLine) break;
    if (await uploadChunk(c, true)) {
      await idbDel(c.key);
      done++;
      onProgress?.(all.length - done);
    } else break;
  }
  return done;
}

function pickMime(): string {
  const cands = ["audio/webm;codecs=opus", "audio/mp4;codecs=mp4a.40.2", "audio/mp4", "audio/webm", "audio/ogg;codecs=opus"];
  for (const m of cands) {
    if (typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported?.(m)) return m;
  }
  return "";
}

export class LiveRecorder {
  private stream: MediaStream | null = null;
  private rec: MediaRecorder | null = null;
  private seq = 0;
  private startedAt = 0;
  private segStart = 0;
  private stopping = false;
  private wake: { release: () => Promise<void> } | null = null;
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private timers: number[] = [];
  private hadGap = false;
  state: RecorderState = {
    recording: false, online: true, queued: 0, uploaded: 0, level: 0, hidden: false, wakeLock: false, error: null,
    elapsed: 0,
  };

  constructor(private recId: number, private onState: (s: RecorderState) => void, startSeq = 0, startOffset = 0) {
    this.seq = startSeq;
    this.startOffset = startOffset;
  }

  private startOffset = 0;

  private emit(patch: Partial<RecorderState>) {
    this.state = { ...this.state, ...patch };
    this.onState(this.state);
  }

  async start() {
    if (!navigator.mediaDevices?.getUserMedia) {
      this.emit({ error: "Dieser Browser erlaubt keine Mikrofonaufnahme." });
      return;
    }
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: false, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch {
      this.emit({ error: "Mikrofon-Zugriff verweigert. Bitte in den Einstellungen erlauben." });
      return;
    }
    this.startedAt = performance.now();
    this.setupMeter();
    await this.requestWakeLock();
    document.addEventListener("visibilitychange", this.onVisibility);
    window.addEventListener("online", this.onOnline);
    window.addEventListener("offline", this.onOffline);
    this.emit({ recording: true, online: navigator.onLine, error: null });
    this.nextSegment();
    this.timers.push(window.setInterval(() => this.emit({ elapsed: (performance.now() - this.startedAt) / 1000 }), 1000));
    this.timers.push(window.setInterval(() => this.retryQueue(), 15000));
  }

  private setupMeter() {
    try {
      const Ctx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.ctx = new Ctx();
      const src = this.ctx.createMediaStreamSource(this.stream!);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 512;
      src.connect(this.analyser);
      const buf = new Uint8Array(this.analyser.fftSize);
      const tick = () => {
        if (!this.analyser || !this.state.recording) return;
        this.analyser.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        this.emit({ level: Math.min(1, Math.sqrt(sum / buf.length) * 4) });
        window.setTimeout(tick, 200);
      };
      tick();
    } catch {
      /* meter is optional */
    }
  }

  private async requestWakeLock() {
    try {
      const nav = navigator as Navigator & { wakeLock?: { request: (t: string) => Promise<{ release: () => Promise<void> }> } };
      if (nav.wakeLock) {
        this.wake = await nav.wakeLock.request("screen");
        this.emit({ wakeLock: true });
      }
    } catch {
      this.emit({ wakeLock: false });
    }
  }

  private onVisibility = () => {
    const hidden = document.visibilityState === "hidden";
    this.emit({ hidden });
    if (!hidden) this.requestWakeLock();
  };

  private onOnline = () => {
    this.emit({ online: true });
    this.retryQueue();
  };

  private onOffline = () => {
    this.hadGap = true;
    this.emit({ online: false });
  };

  private nextSegment() {
    if (!this.stream || this.stopping) return;
    const mime = pickMime();
    const rec = mime ? new MediaRecorder(this.stream, { mimeType: mime, audioBitsPerSecond: 32000 }) : new MediaRecorder(this.stream);
    const parts: Blob[] = [];
    const seq = this.seq++;
    const offset = this.startOffset + (performance.now() - this.startedAt) / 1000;
    this.segStart = performance.now();
    rec.ondataavailable = (e) => e.data.size && parts.push(e.data);
    rec.onstop = () => {
      const duration = (performance.now() - this.segStart) / 1000;
      if (!this.stopping) this.nextSegment();
      const blob = new Blob(parts, { type: rec.mimeType || mime || "audio/webm" });
      if (blob.size > 0) this.handleChunk({ key: `${this.recId}-${seq}`, recId: this.recId, seq, offset_s: offset, duration_s: duration, mime: blob.type, blob });
    };
    rec.start();
    this.rec = rec;
    window.setTimeout(() => rec.state === "recording" && rec.stop(), SEGMENT_MS);
  }

  private async handleChunk(c: QueuedChunk) {
    const late = this.hadGap;
    if (navigator.onLine && (await uploadChunk(c, late))) {
      this.emit({ uploaded: this.state.uploaded + 1 });
      return;
    }
    this.hadGap = true;
    try {
      await idbPut(c);
    } catch {
      this.emit({ error: "Offline-Speicher voll – Abschnitt verloren." });
    }
    this.emit({ queued: await pendingChunks(this.recId), online: navigator.onLine });
  }

  private async retryQueue() {
    if (!navigator.onLine) return;
    const left = await pendingChunks(this.recId);
    if (!left) return;
    await flushQueue((l) => this.emit({ queued: l }));
    this.emit({ queued: await pendingChunks(this.recId) });
  }

  async stop() {
    this.stopping = true;
    if (this.rec && this.rec.state === "recording") {
      await new Promise<void>((res) => {
        const r = this.rec!;
        const prev = r.onstop;
        r.onstop = (ev) => {
          prev?.call(r, ev);
          res();
        };
        r.stop();
      });
    }
    this.stream?.getTracks().forEach((t) => t.stop());
    this.timers.forEach((t) => clearInterval(t));
    document.removeEventListener("visibilitychange", this.onVisibility);
    window.removeEventListener("online", this.onOnline);
    window.removeEventListener("offline", this.onOffline);
    try {
      await this.wake?.release();
    } catch {
      /* ignore */
    }
    await this.ctx?.close().catch(() => undefined);
    this.emit({ recording: false, level: 0, wakeLock: false });
    await new Promise((r) => setTimeout(r, 300));
    await this.retryQueue();
  }
}
