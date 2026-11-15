import { Gif } from "@remotion/gif";
import { Audio } from "@remotion/media";
import React from "react";
import {
  AbsoluteFill, Easing, Img, interpolate, OffthreadVideo, Sequence, spring, staticFile, useCurrentFrame, useVideoConfig,
} from "remotion";
import { DATA } from "./data";
import MOUTH from "./mouth.json";
import RUNS from "./runs.json";

export const DURATION_S = 30;
const FONT = "Inter, system-ui, sans-serif";
const ORANGE = "#ff7a2f", BLUE = "#5aa9ff", VIOLET = "#b07cff", RED = "#ff5c6a";
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const ease = Easing.out(Easing.cubic);

// scene timing = the pauses in the voice-over (ffmpeg silencedetect)
const T = { hook: [0, 4.45], gap: [4.45, 8.8], product: [8.8, 13.05], train: [13.05, 17.3], iss: [17.3, 21.75], moon: [21.75, 23.55], end: [23.55, 29.9] } as const;  // Eve take

// ---------- background: deep space, slowly drifting twinkling stars ----------
const rnd = (i: number) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };
const Stars: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 40%, #16203a 0%, #0a0e1a 55%, #04050a 100%)" }}>
      <svg width="1920" height="1080">
        {Array.from({ length: 170 }, (_, i) => {
          const x = (rnd(i) * 1920 - f * (0.2 + rnd(i + 9) * 0.6) + 1920) % 1920, y = rnd(i + 3) * 1080;
          const tw = 0.35 + 0.65 * Math.abs(Math.sin(f / 22 + i));
          return <circle key={i} cx={x} cy={y} r={0.6 + rnd(i + 5) * 1.6} fill="white" opacity={tw * (0.25 + rnd(i + 7) * 0.6)} />;
        })}
      </svg>
    </AbsoluteFill>
  );
};

// subtitles are not burned in: out/flame-in-freefall-demo.srt goes to YouTube as the English caption track

// ---------- 1. hook: kinetic type ----------
const Hook: React.FC = () => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const n = Math.round(interpolate(f, [12, 50], [0, 30], { ...clamp, easing: ease }));
  const pop = spring({ frame: f - 8, fps, config: { damping: 12 } });
  const sub = interpolate(f, [62, 80], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ fontFamily: FONT, justifyContent: "center", paddingLeft: 170, paddingBottom: 120 }}>
      <div style={{ fontSize: 46, letterSpacing: "0.18em", color: "#9aa6c0", fontWeight: 700, opacity: interpolate(f, [0, 10], [0, 1], clamp) }}>MOON BASES WILL BREATHE</div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 24, transform: `scale(${0.85 + 0.15 * pop})`, transformOrigin: "left center" }}>
        <span style={{ fontSize: 300, fontWeight: 900, lineHeight: 1, background: `linear-gradient(180deg, #ffd25e, ${ORANGE} 60%, #ff3d1f)`,
          WebkitBackgroundClip: "text", color: "transparent", filter: "drop-shadow(0 0 40px rgba(255,122,47,0.45))" }}>{n}%</span>
        <span style={{ fontSize: 110, fontWeight: 800, color: "white" }}>oxygen</span>
      </div>
      <div style={{ fontSize: 42, color: "#c9d2e4", opacity: sub, transform: `translateY(${(1 - sub) * 20}px)` }}>
        Air on Earth is 21 %. More oxygen, and fires start easier and spread faster.</div>
    </AbsoluteFill>
  );
};

// ---------- 2. the gap map, drawn from the real dataset ----------
const CH = { x: 200, y: 150, w: 1340, h: 620 };  // chart box
const px = (psi: number) => CH.x + (Math.log(psi / 3) / Math.log(60 / 3)) * CH.w;
const py = (o2: number) => CH.y + CH.h - ((o2 - 10) / (45 - 10)) * CH.h;
const MOON = [px(10.2), py(30)] as const;
const GapChart: React.FC = () => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const axes = interpolate(f, [0, 18], [0, 1], { ...clamp, easing: ease });
  const line = interpolate(f, [52, 80], [0, 1], { ...clamp, easing: ease });
  const zone = interpolate(f, [78, 96], [0, 1], clamp);
  const star = spring({ frame: f - 92, fps, config: { damping: 9 } });
  const pulse = (f - 92) / 30;
  const col = { s: ORANGE, d: BLUE, g: VIOLET } as Record<string, string>;
  const pts = RUNS as [number, number, string][];
  return (
    <AbsoluteFill style={{ fontFamily: FONT }}>
      <div style={{ position: "absolute", left: CH.x, top: 60, fontSize: 40, fontWeight: 800, color: "white", opacity: axes }}>
        Every NASA microgravity fire test, by oxygen and pressure</div>
      <svg width="1920" height="1080">
        {/* zone above the highest solid test */}
        <rect x={CH.x} y={CH.y} width={CH.w} height={py(22.2) - CH.y} fill={RED} opacity={0.10 * zone} />
        <text x={CH.x + CH.w - 20} y={CH.y + 50} textAnchor="end" fill="#ff9aa3" fontSize="34" fontWeight="800" opacity={zone}>No solid material tested here</text>
        {/* axes */}
        <line x1={CH.x} y1={CH.y + CH.h} x2={CH.x + CH.w * axes} y2={CH.y + CH.h} stroke="#5b6680" strokeWidth="3" />
        <line x1={CH.x} y1={CH.y + CH.h} x2={CH.x} y2={CH.y + CH.h - CH.h * axes} stroke="#5b6680" strokeWidth="3" />
        {[15, 20, 25, 30, 35, 40].map((o) => <g key={o} opacity={axes}><line x1={CH.x} x2={CH.x + CH.w} y1={py(o)} y2={py(o)} stroke="#2a3348" strokeWidth="1" />
          <text x={CH.x - 16} y={py(o) + 10} textAnchor="end" fill="#8a96b0" fontSize="26">{o}%</text></g>)}
        {[4, 8, 14.7, 30, 60].map((p) => <text key={p} x={px(p)} y={CH.y + CH.h + 40} textAnchor="middle" fill="#8a96b0" fontSize="26" opacity={axes}>{p} psi</text>)}
        <text x={CH.x - 110} y={CH.y - 20} fill="#8a96b0" fontSize="26" opacity={axes}>oxygen</text>
        {/* runs pop in, left to right */}
        {pts.map(([p, o, fam], i) => {
          if (p < 3 || p > 60 || o < 10 || o > 45) return null;
          const at = 14 + (px(p) - CH.x) / CH.w * 34 + rnd(i) * 6;
          const k = interpolate(f, [at, at + 6], [0, 1], clamp);
          return k > 0 ? <circle key={i} cx={px(p) + (rnd(i + 1) - 0.5) * 10} cy={py(o) + (rnd(i + 2) - 0.5) * 6} r={(fam === "s" ? 7 : 4.5) * k}
            fill={col[fam]} opacity={fam === "s" ? 0.95 : 0.55} /> : null;
        })}
        {/* highest solid ever tested */}
        <line x1={CH.x} x2={CH.x + CH.w * line} y1={py(22.2)} y2={py(22.2)} stroke={ORANGE} strokeWidth="4" strokeDasharray="14 10" />
        <text x={CH.x + 16} y={py(22.2) - 16} fill={ORANGE} fontSize="30" fontWeight="800" opacity={line}>22.2 %: highest solid ever burned in microgravity</text>
        {/* the Moon base */}
        {star > 0.01 ? <g transform={`translate(${MOON[0]} ${MOON[1]}) scale(${star})`}>
          {[0, 1].map((r) => <circle key={r} r={30 + ((pulse + r * 0.5) % 1) * 60} fill="none" stroke="#ffd25e" strokeWidth="3" opacity={1 - ((pulse + r * 0.5) % 1)} />)}
          <path d="M0 -30 L8.8 -9.3 L28.5 -9.3 L12.6 3.6 L18.5 24.3 L0 12 L-18.5 24.3 L-12.6 3.6 L-28.5 -9.3 L-8.8 -9.3 Z" fill="#ffd25e" />
          <text x="44" y="-6" fill="white" fontSize="34" fontWeight="800">Moon base</text>
          <text x="44" y="30" fill="#c9d2e4" fontSize="26">30 % O₂ · 10.2 psi</text>
        </g> : null}
        {/* legend */}
        {[["solid materials", ORANGE], ["fuel droplets", BLUE], ["gas flames", VIOLET]].map(([t, c], i) =>
          <g key={t} opacity={axes} transform={`translate(${CH.x + 20 + i * 260} ${CH.y + CH.h + 90})`}><circle r="8" fill={c} /><text x="18" y="9" fill="#c9d2e4" fontSize="26">{t}</text></g>)}
      </svg>
    </AbsoluteFill>
  );
};

// ---------- 3. the product in a tilted browser, pushing into the side-by-side ----------
const Product: React.FC = () => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const inn = spring({ frame: f, fps, config: { damping: 18 } });
  const push = interpolate(f, [40, 100], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  const W = 1240 * 1.05, H = 800 * 1.05;
  const ring = interpolate(f, [92, 108], [0, 1], clamp);
  return (
    <AbsoluteFill style={{ fontFamily: FONT, perspective: 1800, alignItems: "center", justifyContent: "center", paddingBottom: 60 }}>
      <div style={{ width: W, height: H + 46, borderRadius: 18, overflow: "hidden", background: "#0f131c", border: "1px solid #2b3245",
        boxShadow: "0 40px 120px rgba(0,0,0,0.6), 0 0 80px rgba(255,122,47,0.12)",
        transform: `translateY(${(1 - inn) * 200}px) rotateY(${-16 * (1 - push)}deg) rotateX(${7 * (1 - push)}deg)
          scale(${0.82 + push * 0.42}) translate(${-push * 230}px, ${-push * 210}px)` }}>
        <div style={{ height: 46, display: "flex", alignItems: "center", gap: 10, padding: "0 18px", background: "#161b27", borderBottom: "1px solid #2b3245" }}>
          {["#ff5f57", "#febc2e", "#28c840"].map((c) => <div key={c} style={{ width: 14, height: 14, borderRadius: 7, background: c }} />)}
          <div style={{ marginLeft: 16, flex: 1, height: 28, borderRadius: 8, background: "#0b0e15", color: "#8a96b0", fontSize: 18, display: "flex", alignItems: "center", paddingLeft: 14 }}>
            flame-in-freefall-ivory.vercel.app/#scenario</div>
        </div>
        <div style={{ position: "relative" }}>
          <Img src={staticFile("shots/s3_browser.png")} style={{ width: W, height: H, display: "block" }} />
          <div style={{ position: "absolute", left: W * 0.435, top: H * 0.425, width: W * 0.565, height: H * 0.56, borderRadius: 14,
            border: `5px solid ${ORANGE}`, opacity: ring, boxShadow: `0 0 ${30 * ring}px ${ORANGE}`, transform: `scale(${1.06 - 0.06 * ring})` }} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

// ---------- 4. training: real NASA footage next to our simulation, then the numbers ----------
const Counter: React.FC<{ to: number; dec?: number; pre?: string; post?: string; at: number }> = ({ to, dec = 0, pre = "", post = "", at }) => {
  const f = useCurrentFrame();
  const v = interpolate(f, [at, at + 24], [0, to], { ...clamp, easing: ease });
  return <>{pre}{v.toFixed(dec)}{post}</>;
};
const Training: React.FC = () => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const a = spring({ frame: f, fps, config: { damping: 16 } }), b = spring({ frame: f - 6, fps, config: { damping: 16 } });
  const panel = (k: number): React.CSSProperties => ({ width: 760, height: 470, borderRadius: 18, overflow: "hidden", background: "black",
    border: "1px solid #2b3245", boxShadow: "0 30px 80px rgba(0,0,0,0.5)", opacity: k, transform: `translateY(${(1 - k) * 60}px)` });
  const label = (t: string, c: string) => <div style={{ position: "absolute", left: 18, top: 14, fontSize: 24, fontWeight: 800, color: c,
    background: "rgba(6,8,14,0.8)", padding: "6px 14px", borderRadius: 10 }}>{t}</div>;
  const cards: [React.ReactNode, string][] = [
    [<Counter key="a" to={384} at={40} />, "NASA flame videos measured"],
    [<><Counter key="b" to={30} at={48} /> / 31</>, "solid fires predicted unseen"],
    [<Counter key="c" to={1.42} dec={2} pre="×" at={56} />, `gas flame-out time error (guessing ${DATA.gasGuess})`],
  ];
  return (
    <AbsoluteFill style={{ fontFamily: FONT }}>
      <div style={{ position: "absolute", top: 50, width: "100%", display: "flex", justifyContent: "center", gap: 40 }}>
        <div style={{ ...panel(a), position: "relative" }}>
          <OffthreadVideo src={staticFile("nasa_b8.mp4")} startFrom={60} muted style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          {label("REAL · NASA BASS-II run B8 (ISS)", "#9ccaff")}
        </div>
        <div style={{ ...panel(b), position: "relative" }}>
          <OffthreadVideo src={staticFile("sim_b8.mp4")} muted style={{ width: "100%", height: "100%", objectFit: "contain" }} />
          {label("OUR SIMULATION · same conditions", "#ffb27a")}
        </div>
      </div>
      <div style={{ position: "absolute", top: 560, width: "100%", display: "flex", justifyContent: "center", gap: 30 }}>
        {cards.map(([n, t], i) => {
          const k = spring({ frame: f - 34 - i * 8, fps, config: { damping: 14 } });
          return (
            <div key={t} style={{ width: 470, padding: "20px 24px", borderRadius: 20, background: "rgba(18,21,30,0.92)", border: `1px solid ${ORANGE}66`,
              textAlign: "center", opacity: k, transform: `translateY(${(1 - k) * 40}px)` }}>
              <div style={{ fontSize: 84, fontWeight: 900, color: "#ffa25a", lineHeight: 1 }}>{n}</div>
              <div style={{ fontSize: 28, color: "#d7dbe4", marginTop: 10 }}>{t}</div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

// ---------- 5/6. the burn, as a frame sequence from the Inspect & ignite page ----------
const Badge: React.FC<{ text: string; color: string; at: number }> = ({ text, color, at }) => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const k = spring({ frame: f - at, fps, config: { damping: 12 } });
  return <div style={{ position: "absolute", left: 300, top: 120, fontFamily: FONT, fontSize: 38, fontWeight: 800, color, padding: "10px 22px",
    borderRadius: 14, background: "rgba(6,8,14,0.85)", border: `2px solid ${color}`, transform: `scale(${k})`, transformOrigin: "left center" }}>{text}</div>;
};
const Fire: React.FC<{ part: "iss" | "moon" }> = ({ part }) => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const k = spring({ frame: f, fps, config: { damping: 20 } });
  // frames captured at 20 fps from the Inspect & ignite page (deterministic capture mode); ISS: one continuous fire,
  // fans cut at sim second 3.6 = captured frame 41 = video frame 61
  // fire_i.mp4 / fire_m.mp4: the captured frames blended to 30 fps (one continuous, repeatable burn); fans cut at
  // captured frame 41 = video frame 61
  const issSplit = 61;
  const glow = part === "iss" && f >= issSplit ? interpolate(f, [issSplit, issSplit + 50], [0.5, 0], clamp) : 0.5;
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", paddingBottom: 110 }}>
      <div style={{ width: 1200, height: 800, borderRadius: 26, overflow: "hidden", border: "1px solid #2b3245", transform: `scale(${0.9 + 0.1 * k})`,
        boxShadow: `0 40px 120px rgba(0,0,0,0.6), 0 0 140px rgba(255,90,30,${glow})` }}>
        <OffthreadVideo src={staticFile(part === "moon" ? "fire_m.mp4" : "fire_i.mp4")} muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
      </div>
      {part === "iss" ? <>
        <Sequence durationInFrames={issSplit} layout="none"><Badge text="ISS · fans on: it spreads" color="#ffb27a" at={4} /></Sequence>
        <Sequence from={issSplit} layout="none"><Badge text="Fans off: starved of oxygen, it goes out" color="#7ee8b8" at={0} /></Sequence>
      </> : <Badge text="Moon base · fans off: still burning" color="#ff8a8a" at={2} />}
    </AbsoluteFill>
  );
};

// ---------- 7. end card ----------
const End: React.FC = () => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const title = "Flame in Freefall";
  return (
    <AbsoluteFill style={{ fontFamily: FONT, alignItems: "center", justifyContent: "center", paddingTop: 140 }}>
      <div style={{ display: "flex", fontSize: 130, fontWeight: 900, color: "white" }}>
        {title.split("").map((ch, i) => {
          const k = spring({ frame: f - 10 - i * 2, fps, config: { damping: 12 } });
          return <span key={i} style={{ display: "inline-block", whiteSpace: "pre", transform: `translateY(${(1 - k) * 60}px)`, opacity: k }}>{ch}</span>;
        })}
      </div>
      <div style={{ fontSize: 44, color: "#ffa25a", fontWeight: 700, marginTop: 12, opacity: interpolate(f, [40, 56], [0, 1], clamp) }}>flame-in-freefall-ivory.vercel.app</div>
      <div style={{ fontSize: 30, color: "#a9b1c2", marginTop: 14, opacity: interpolate(f, [52, 68], [0, 1], clamp) }}>
        NASA Space Apps 2026 · built on NASA's PSI microgravity combustion data</div>
    </AbsoluteFill>
  );
};

// ---------- Ember: walks between spots, faces what it talks about, bounces with the voice ----------
const STOPS: { at: number; end: number; pos: [number, number]; face?: number }[] = [
  { at: 0, end: 4.45, pos: [1560, 520], face: 1100 },
  { at: 4.45, end: 8.8, pos: [MOON[0] + 560, MOON[1] + 30], face: MOON[0] },
  { at: 8.8, end: 13.05, pos: [200, 760], face: 1200 },
  { at: 13.05, end: 17.3, pos: [1790, 620], face: 1000 },
  { at: 17.3, end: 23.55, pos: [1660, 640], face: 900 },
  { at: 23.55, end: 30.0, pos: [960, 300] },
];
const SIZE = 240, MOVE = 0.9;
const posAt = (s: number): [number, number] => {
  const i = Math.max(0, STOPS.findIndex((st) => s >= st.at && s < st.end));
  const st = STOPS[i], prev = STOPS[Math.max(0, i - 1)];
  const k = interpolate(s, [st.at, st.at + MOVE], [0, 1], { ...clamp, easing: Easing.inOut(Easing.cubic) });
  return [prev.pos[0] + (st.pos[0] - prev.pos[0]) * k, prev.pos[1] + (st.pos[1] - prev.pos[1]) * k];
};
const Ember: React.FC = () => {
  const f = useCurrentFrame(), { fps } = useVideoConfig(), s = f / fps;
  const [x, y] = posAt(s), [px0] = posAt(Math.max(0, s - 1 / fps));
  const vx = (x - px0) * fps;
  const st = STOPS.find((q) => s >= q.at && s < q.end) ?? STOPS[STOPS.length - 1];
  const flip = st.face !== undefined && Math.abs(vx) < 5 ? st.face < x : vx < -5;
  const mouth = (MOUTH as number[])[Math.min(f, MOUTH.length - 1)] ?? 0;
  const lean = Math.max(-18, Math.min(18, -vx * 0.012));
  const hop = Math.abs(Math.sin(s * 11)) * 16 * Math.min(1, Math.abs(vx) / 400);
  const entry = spring({ frame: f, fps, config: { damping: 10 } });
  const talk = 1 + mouth * 0.08, squash = 1 - mouth * 0.04;
  return (
    <div style={{ position: "absolute", left: x - SIZE / 2, top: y - SIZE / 2 - hop, width: SIZE, height: SIZE,
      transform: `rotate(${lean}deg) scale(${(flip ? -1 : 1) * squash * entry}, ${talk * entry})`, transformOrigin: "50% 85%",
      filter: "drop-shadow(0 0 30px rgba(255,122,47,0.45)) drop-shadow(0 16px 24px rgba(0,0,0,0.6))" }}>
      <Gif src={staticFile("ember.gif")} width={SIZE} height={SIZE} fit="contain" />
    </div>
  );
};

export const Demo: React.FC = () => {
  const { fps } = useVideoConfig();
  const seqOf = (k: keyof typeof T) => ({ from: Math.round(T[k][0] * fps), durationInFrames: Math.round((T[k][1] - T[k][0]) * fps) });
  return (
    <AbsoluteFill style={{ backgroundColor: "#04050a" }}>
      <Stars />
      <Sequence name="Hook" {...seqOf("hook")}><Hook /></Sequence>
      <Sequence name="Gap map" {...seqOf("gap")}><GapChart /></Sequence>
      <Sequence name="Product" {...seqOf("product")}><Product /></Sequence>
      <Sequence name="Training" {...seqOf("train")}><Training /></Sequence>
      <Sequence name="Fire ISS" {...seqOf("iss")}><Fire part="iss" /></Sequence>
      <Sequence name="Fire Moon" {...seqOf("moon")}><Fire part="moon" /></Sequence>
      <Sequence name="End" {...seqOf("end")}><End /></Sequence>
      <Ember />
      <Audio src={staticFile("voice_eve.mp3")} />
    </AbsoluteFill>
  );
};
