import React from "react";

// Ember, drawn: orange flame on top, round blue face, black stick arms and legs (same look as public/img/ember.gif).
// Everything is driven by props so the video can make it talk, point, walk, blink and wave.
export type EmberPose = {
  mouth: number;            // 0 = closed (smile) .. 1 = wide open, from the voice loudness
  t: number;                // seconds, for flicker / blink / walk cycles
  walk: number;             // 0 = standing .. 1 = full stride
  point?: { angle: number; amount: number };  // right arm: direction in degrees (0 = right, 90 = down), 0..1 raised
  wave?: number;            // 0..1 left arm waving
};

const INK = "#20242e", HALO = "#fff3e0";
// a dark stick limb with a light halo underneath (readable on the dark website screenshots)
const Limb: React.FC<{ d: string; w?: number }> = ({ d, w = 7 }) => (
  <g fill="none" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} stroke={HALO} strokeWidth={w + 6} /><path d={d} stroke={INK} strokeWidth={w} />
  </g>
);

export const EmberCharacter: React.FC<{ size: number; pose: EmberPose }> = ({ size, pose }) => {
  const { mouth, t, walk, point, wave = 0 } = pose;
  const flick = (k: number, f: number) => Math.sin(t * f + k) * 4;
  // flame: three tongues that flicker
  const flame = `M100 18 C ${112 + flick(1, 9)} 40, ${126} 52, 132 70 C ${140 + flick(2, 11)} 52, ${150} 46, ${158 + flick(3, 8)} 34
    C 162 70, 172 100, 166 130 L 34 130 C 26 100, 36 72, ${44 + flick(4, 10)} 40 C 52 58, 60 62, 66 72 C 70 52, ${84 + flick(5, 12)} 36, 100 18 Z`;
  const blink = (t % 3.3) > 3.15 ? 0.15 : 1;
  const mo = Math.max(0, Math.min(1, mouth));
  // arms: shoulders on the face sides; the right arm swings from hanging (60°) toward the pointing direction
  const sh = { r: [158, 168], l: [42, 168] };
  const pa = point ? point.amount : 0;
  const rAng = ((1 - pa) * 60 + pa * (point?.angle ?? 60)) * (Math.PI / 180);
  const rEl = [sh.r[0] + Math.cos(rAng) * 34, sh.r[1] + Math.sin(rAng) * 34];
  const rHand = [rEl[0] + Math.cos(rAng) * 30, rEl[1] + Math.sin(rAng) * 30];
  const wAng = (-110 + Math.sin(t * 10) * 25 * wave) * (Math.PI / 180);
  const lAng = ((1 - wave) * 120 + wave * (wAng * 180 / Math.PI)) * (Math.PI / 180) + Math.sin(t * 3) * 0.08 * (1 - wave);
  const lEl = [sh.l[0] + Math.cos(lAng) * 32, sh.l[1] + Math.sin(lAng) * 32];
  const lHand = [lEl[0] + Math.cos(lAng) * 28, lEl[1] + Math.sin(lAng) * 28];
  // legs: swing while walking
  const sw = Math.sin(t * 12) * 22 * walk;
  const leg = (x: number, a: number) => {
    const r = (90 + a) * Math.PI / 180;
    const knee = [x + Math.cos(r) * 26, 222 + Math.sin(r) * 26];
    const foot = [knee[0] + Math.cos(r) * 22, knee[1] + Math.sin(r) * 22];
    return { d: `M${x} 222 L${knee[0]} ${knee[1]} L${foot[0]} ${foot[1]}`, foot };
  };
  const L1 = leg(84, sw), L2 = leg(116, -sw);
  return (
    <svg width={size} height={size * 1.4} viewBox="0 0 200 280" style={{ overflow: "visible" }}>
      <defs>
        <linearGradient id="fl" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#ff4d1a" /><stop offset="0.55" stopColor="#ff9a2e" /><stop offset="1" stopColor="#ffd25e" />
        </linearGradient>
        <radialGradient id="face" cx="0.5" cy="0.3" r="0.75">
          <stop offset="0" stopColor="#fff1a8" /><stop offset="0.35" stopColor="#ffc35a" /><stop offset="0.62" stopColor="#7fd4ff" /><stop offset="1" stopColor="#2f7dff" />
        </radialGradient>
        <radialGradient id="glow" cx="0.5" cy="0.55" r="0.5">
          <stop offset="0" stopColor="#ff8a3d" stopOpacity="0.55" /><stop offset="1" stopColor="#ff8a3d" stopOpacity="0" />
        </radialGradient>
      </defs>
      <ellipse cx="100" cy="150" rx="118" ry="128" fill="url(#glow)" />
      {/* legs behind the body */}
      <Limb d={L1.d} /><Limb d={L2.d} />
      <ellipse cx={L1.foot[0] + 4} cy={L1.foot[1] + 2} rx="10" ry="5" fill={INK} stroke={HALO} strokeWidth="3" />
      <ellipse cx={L2.foot[0] + 4} cy={L2.foot[1] + 2} rx="10" ry="5" fill={INK} stroke={HALO} strokeWidth="3" />
      <path d={flame} fill="url(#flame)" style={{ fill: "url(#fl)" }} />
      <circle cx="100" cy="160" r="66" fill="url(#face)" />
      {/* eyes */}
      <ellipse cx="78" cy="150" rx="7" ry={10 * blink} fill={INK} />
      <ellipse cx="122" cy="150" rx="7" ry={10 * blink} fill={INK} />
      <circle cx="80" cy="146" r="2.4" fill="white" opacity={blink} /><circle cx="124" cy="146" r="2.4" fill="white" opacity={blink} />
      {/* cheeks */}
      <ellipse cx="64" cy="170" rx="9" ry="5" fill="#ff7a6b" opacity="0.45" /><ellipse cx="136" cy="170" rx="9" ry="5" fill="#ff7a6b" opacity="0.45" />
      {/* mouth: smile when quiet, opens with the voice */}
      {mo < 0.12 ? (
        <path d="M86 176 Q100 188 114 176" stroke={INK} strokeWidth="5" fill="none" strokeLinecap="round" />
      ) : (
        <g>
          <ellipse cx="100" cy={180} rx={11 + mo * 5} ry={3 + mo * 13} fill="#5a1620" />
          <ellipse cx="100" cy={184 + mo * 7} rx={7 + mo * 3} ry={2 + mo * 4} fill="#ff8f9a" />
        </g>
      )}
      {/* arms in front */}
      <Limb d={`M${sh.r[0]} ${sh.r[1]} L${rEl[0]} ${rEl[1]} L${rHand[0]} ${rHand[1]}`} />
      {pa > 0.6 ? <Limb d={`M${rHand[0]} ${rHand[1]} l${Math.cos(rAng) * 14} ${Math.sin(rAng) * 14}`} w={5} /> : null}
      <circle cx={rHand[0]} cy={rHand[1]} r="8" fill={INK} stroke={HALO} strokeWidth="3" />
      <Limb d={`M${sh.l[0]} ${sh.l[1]} L${lEl[0]} ${lEl[1]} L${lHand[0]} ${lHand[1]}`} />
      <circle cx={lHand[0]} cy={lHand[1]} r="8" fill={INK} stroke={HALO} strokeWidth="3" />
    </svg>
  );
};
