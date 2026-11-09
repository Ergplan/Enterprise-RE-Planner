"use client";

import { useEffect, useRef, useState } from "react";

type Mode = "intake" | "plan";
type Line = { who: "you" | "ergplan" | "tool"; text: string };
type ToolOut = { state: Record<string, unknown>; say: string; ok: boolean };

// Voice and text with the same tools. Voice: an ephemeral OpenAI Realtime secret from the API, WebRTC
// from the browser, tool calls relayed to /api/voice/tool. Text: /api/chat runs the tools server-side.
// The voice only takes inputs and reads results back; every number it says came from a tool.
export function VoicePanel({ mode, token, onState, intro, initialState, compact }: {
  mode: Mode; token?: string; onState?: (s: Record<string, unknown>) => void; intro: string;
  initialState?: Record<string, unknown>; compact?: boolean;
}) {
  const [lines, setLines] = useState<Line[]>([]);
  const [live, setLive] = useState(false);
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const state = useRef<Record<string, unknown>>(initialState ?? {});
  // the form is the truth: whatever the page has typed since is what the tools work on
  useEffect(() => {
    if (initialState) state.current = initialState;
  }, [initialState]);
  const pc = useRef<RTCPeerConnection | null>(null);
  const history = useRef<{ role: string; content: string }[]>([]);

  useEffect(() => () => pc.current?.close(), []);

  const say = (l: Line) => setLines((x) => [...x, l]);
  const setState = (s: Record<string, unknown>) => {
    state.current = s;
    onState?.(s);
  };

  async function runTool(name: string, args: Record<string, unknown>): Promise<ToolOut> {
    const r = await fetch("/api/voice/tool", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, name, arguments: args, state: state.current, token }) });
    const out = (await r.json()) as ToolOut;
    if (out.state) setState(out.state);
    say({ who: "tool", text: out.say });
    return out;
  }

  async function startVoice() {
    setError("");
    setBusy(true);
    try {
      const r = await fetch("/api/voice/session", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, token }) });
      if (!r.ok) throw new Error(r.status === 503 ? "Voice is not set up on this server; type below instead." : `voice: ${r.status}`);
      const sess = (await r.json()) as { client_secret: string; model: string };
      const peer = new RTCPeerConnection();
      pc.current = peer;
      const audio = new Audio();
      audio.autoplay = true;
      peer.ontrack = (e) => {
        audio.srcObject = e.streams[0];
      };
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      peer.addTrack(mic.getTracks()[0]);
      const dc = peer.createDataChannel("oai-events");
      dc.onmessage = async (e) => {
        const ev = JSON.parse(e.data as string) as { type: string; name?: string; call_id?: string; arguments?: string; transcript?: string };
        if (ev.type === "response.function_call_arguments.done" && ev.name && ev.call_id) {
          const out = await runTool(ev.name, JSON.parse(ev.arguments || "{}") as Record<string, unknown>);
          dc.send(JSON.stringify({ type: "conversation.item.create", item: { type: "function_call_output", call_id: ev.call_id, output: out.say } }));
          dc.send(JSON.stringify({ type: "response.create" }));
        } else if (ev.type === "conversation.item.input_audio_transcription.completed" && ev.transcript) {
          say({ who: "you", text: ev.transcript });
        } else if (ev.type === "response.output_audio_transcript.done" && ev.transcript) {
          say({ who: "ergplan", text: ev.transcript });
        }
      };
      const offer = await peer.createOffer();
      await peer.setLocalDescription(offer);
      const ans = await fetch(`https://api.openai.com/v1/realtime/calls?model=${encodeURIComponent(sess.model)}`, {
        method: "POST",
        body: offer.sdp,
        headers: { Authorization: `Bearer ${sess.client_secret}`, "Content-Type": "application/sdp" },
      });
      if (!ans.ok) throw new Error(`voice connection: ${ans.status}`);
      await peer.setRemoteDescription({ type: "answer", sdp: await ans.text() });
      setLive(true);
      say({ who: "ergplan", text: intro });
    } catch (e) {
      setError((e as Error).message);
      pc.current?.close();
    } finally {
      setBusy(false);
    }
  }

  function stopVoice() {
    pc.current?.close();
    pc.current = null;
    setLive(false);
  }

  async function send() {
    const msg = text.trim();
    if (!msg) return;
    setText("");
    setError("");
    say({ who: "you", text: msg });
    history.current.push({ role: "user", content: msg });
    setBusy(true);
    try {
      const r = await fetch("/api/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ mode, messages: history.current, state: state.current, token }) });
      if (!r.ok) throw new Error(r.status === 503 ? "Chat is not set up on this server." : `chat: ${r.status}`);
      const out = (await r.json()) as { reply: string; state: Record<string, unknown>; tool_results: { say: string }[] };
      setState(out.state);
      for (const t of out.tool_results) say({ who: "tool", text: t.say });
      if (out.reply) {
        say({ who: "ergplan", text: out.reply });
        history.current.push({ role: "assistant", content: out.reply });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`ep-voice${compact ? " ep-voice--compact" : ""}`}>
      <div className="ep-row">
        {live ? (
          <button className="eg-btn eg-btn--ghost eg-btn--sm" onClick={stopVoice}><span data-icon="mic" data-size="16"></span>End the call</button>
        ) : (
          <button className={`eg-btn eg-btn--sm${compact ? " eg-btn--ghost" : " eg-btn--primary"}`} disabled={busy} onClick={startVoice}><span data-icon="mic" data-size="16"></span>{busy ? "Connecting…" : "Talk"}</button>
        )}
        <span className="eg-muted ep-small">{live ? "Listening. The voice sets values and reads back results; it never works out a number itself." : intro}</span>
      </div>
      {lines.length > 0 && (
        <ol className="ep-transcript" aria-live="polite">
          {lines.map((l, i) => (
            <li key={i} className={`ep-transcript__${l.who}`}><span className="eg-overline">{l.who === "tool" ? "set" : l.who}</span> {l.text}</li>
          ))}
        </ol>
      )}
      <div className="ep-row">
        <span className="eg-input" style={{ flex: 1 }}>
          <input aria-label="Type instead" placeholder={mode === "intake" ? "e.g. our contract demand is 5,000 kVA at 33 kV" : "e.g. what if solar costs ₹3.40?"} value={text}
            onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void send(); }} />
        </span>
        <button className="eg-btn eg-btn--ghost" disabled={busy || !text.trim()} onClick={send}>Send</button>
      </div>
      {error && <p className="ep-error">{error}</p>}
    </div>
  );
}
