import { Gif } from "@remotion/gif";
import React from "react";
import { AbsoluteFill, Easing, Img, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { CAPTIONS, DATA } from "./data";

const FONT = "Inter, system-ui, sans-serif";
// scene start (seconds), length (seconds), screenshot
const SCENES: { at: number; len: number; img: string }[] = [
  { at: 0, len: 3.5, img: "shots/s1_home.png" },
  { at: 3.5, len: 5, img: "shots/s2_gap.png" },
  { at: 8.5, len: 5.5, img: "shots/s3_scenario.png" },
  { at: 14, len: 5.5, img: "shots/s4_compare.png" },
  { at: 19.5, len: 5.5, img: "shots/s5_habitat.png" },
  { at: 25, len: 5, img: "shots/s6_ask.png" },
];
export const DURATION_S = 30;

// A screenshot with a slow push-in and a short fade in.
const Shot: React.FC<{ img: string; len: number; dim?: number }> = ({ img, len, dim = 0 }) => {
  const f = useCurrentFrame(), { fps } = useVideoConfig();
  const zoom = interpolate(f, [0, len * fps], [1.0, 1.06]);
  const fade = interpolate(f, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0d12", opacity: fade }}>
      <Img src={staticFile(img)} style={{ width: "100%", height: "100%", objectFit: "cover", transform: `scale(${zoom})` }} />
      {dim ? <AbsoluteFill style={{ backgroundColor: `rgba(7,9,14,${dim})` }} /> : null}
    </AbsoluteFill>
  );
};

const Caption: React.FC<{ text: string }> = ({ text }) => {
  const f = useCurrentFrame();
  const y = interpolate(f, [0, 10], [30, 0], { extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  return (
    <AbsoluteFill style={{ justifyContent: "flex-end", alignItems: "center", paddingBottom: 90 }}>
      <div style={{ fontFamily: FONT, fontSize: 50, fontWeight: 700, color: "white", background: "rgba(10,12,18,0.82)",
        padding: "18px 34px", borderRadius: 18, maxWidth: 1500, textAlign: "center", transform: `translateY(${y}px)`,
        border: "1px solid rgba(255,255,255,0.12)" }}>{text}</div>
    </AbsoluteFill>
  );
};

// Training beat: three numbers counting in over the simulation-vs-NASA screenshot.
const Stats: React.FC = () => {
  const f = useCurrentFrame();
  const cards = [
    [DATA.videos, "NASA flame videos measured"],
    [DATA.solidFate, "solid fires: burns or goes out, as NASA saw"],
    [DATA.gasTime, `gas flame-out time error (guessing: ${DATA.gasGuess})`],
  ];
  return (
    <AbsoluteFill style={{ flexDirection: "row", justifyContent: "center", alignItems: "center", gap: 40, paddingBottom: 160 }}>
      {cards.map(([n, label], i) => {
        const t = interpolate(f, [10 + i * 12, 28 + i * 12], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.back(1.4)) });
        return (
          <div key={label} style={{ fontFamily: FONT, width: 470, padding: "34px 30px", borderRadius: 24, background: "rgba(18,21,30,0.92)",
            border: "1px solid #ff7a2f66", opacity: t, transform: `translateY(${(1 - t) * 40}px) scale(${0.9 + 0.1 * t})`, textAlign: "center" }}>
            <div style={{ fontSize: 96, fontWeight: 800, color: "#ff9a52", lineHeight: 1 }}>{n}</div>
            <div style={{ fontSize: 34, color: "#d7dbe4", marginTop: 14 }}>{label}</div>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};

// Ember walks between spots, leans against its motion and bobs while talking.
const PATH: [number, number, number][] = [  // [second, x, y] of Ember's feet-ish centre
  [0, -200, 760], [1.6, 300, 720], [3.5, 300, 720], [5, 1450, 380], [8.5, 1450, 380], [10, 1650, 760],
  [14, 1650, 760], [15.2, 200, 300], [19.5, 200, 300], [21, 1500, 300], [25, 1500, 300], [26.5, 960, 560], [30, 960, 560],
];
const Ember: React.FC = () => {
  const f = useCurrentFrame(), { fps } = useVideoConfig(), s = f / fps;
  const ts = PATH.map((p) => p[0]);
  const x = interpolate(s, ts, PATH.map((p) => p[1]), { easing: Easing.inOut(Easing.cubic) });
  const y = interpolate(s, ts, PATH.map((p) => p[2]), { easing: Easing.inOut(Easing.cubic) });
  const vx = x - interpolate(Math.max(0, s - 1 / fps), ts, PATH.map((p) => p[1]), { easing: Easing.inOut(Easing.cubic) });
  const lean = Math.max(-25, Math.min(25, -vx * 0.6));  // moving right → tilt left
  const bob = Math.sin(s * 9) * 8;
  const size = s > 25 ? interpolate(s, [25, 26.5], [260, 380], { extrapolateRight: "clamp" }) : 260;
  return (
    <div style={{ position: "absolute", left: x - size / 2, top: y - size / 2 + bob, width: size, height: size,
      transform: `rotate(${lean}deg)`, filter: "drop-shadow(0 12px 30px rgba(255,122,47,0.45))" }}>
      <Gif src={staticFile("ember-logo.gif")} width={size} height={size} fit="contain" />
    </div>
  );
};

export const Demo: React.FC = () => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ backgroundColor: "#0b0d12" }}>
      {SCENES.map((sc, i) => (
        <Sequence key={sc.img} name={`Scene ${i + 1}`} from={Math.round(sc.at * fps)} durationInFrames={Math.round(sc.len * fps)}>
          <Shot img={sc.img} len={sc.len} dim={i === 3 ? 0.55 : i === 5 ? 0.2 : 0} />
          {i === 3 ? <Stats /> : null}
          <Caption text={CAPTIONS[i]} />
        </Sequence>
      ))}
      <Ember />
    </AbsoluteFill>
  );
};
