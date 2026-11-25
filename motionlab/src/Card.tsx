// 원픽 가운데 카드(920×860)를 채우는 모션 그래픽 — 대본 기반 장면 목록(props)으로 렌더
// 장면 종류: counter(숫자 카운터+선 그래프), tiles(지표 타일 2~3개), bars(하락·상승률 막대),
//           gauge(위험 계기판), headline(기사 헤드라인), point(핵심 문구)
// 색: 남색 바탕, 노랑 #FFD60A, 빨강(상승) #FF4D5A, 파랑(하락) #4D8DFF — 한국식 등락 색
import React from "react";
import "pretendard/dist/web/static/pretendard.css";
import { AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";

const Y = "#FFD60A", UP = "#FF4D5A", DN = "#4D8DFF", BG = "#0A0E18", PANEL = "#121A2B", LINE = "rgba(255,214,10,0.35)";
const font = "Pretendard, sans-serif";
const MUTED = "rgba(255,255,255,0.75)";

export type Item = { label?: string; name?: string; value?: string; change?: string; dir?: string; icon?: string; at?: number; pct?: number };
export type Scene = { type: string; from: number; to: number; label?: string; value?: string; change?: string; dir?: string;
  title?: string; items?: Item[]; level?: number; text?: string; badge?: string; source?: string; date?: string;
  key?: string; sub?: string; at?: number };
export type CardProps = { scenes: Scene[]; tag: string; total: number };

const col = (dir?: string) => (dir === "up" ? UP : dir === "down" ? DN : Y);
const arrow = (dir?: string) => (dir === "up" ? "▲" : dir === "down" ? "▼" : "");

const useIn = (delay = 0) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: f - delay, fps, config: { damping: 14, stiffness: 120 } });
};

// "4,708.53", "1,343.7원", "52억 달러" → 숫자 부분을 세어 올라가게 (앞뒤 글자는 그대로)
const Count: React.FC<{ value: string; delay: number; from?: number; dur?: number }> = ({ value, delay, from = 0.82, dur = 40 }) => {
  const f = useCurrentFrame();
  const m = value.match(/^(.*?)(\d[\d,]*(?:\.\d+)?)(.*)$/);
  if (!m) return <>{value}</>;
  const num = parseFloat(m[2].replace(/,/g, ""));
  const dec = (m[2].split(".")[1] || "").length;
  const t = interpolate(f, [delay, delay + dur], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const v = num * from + (num - num * from) * t;
  const s = m[2].includes(",") ? v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec }) : v.toFixed(dec);
  return <>{m[1]}{s}{m[3]}</>;
};

const Panel: React.FC<{ children: React.ReactNode; h?: number; pad?: string }> = ({ children, h = 680, pad = "40px 52px" }) => {
  const s = useIn(0);
  return (
    <div style={{ width: 840, height: h, background: PANEL, borderRadius: 28, border: `2px solid ${LINE}`, position: "relative",
      boxShadow: "0 0 40px rgba(255,214,10,0.12)", opacity: s, transform: `translateY(${(1 - s) * 50}px)`, padding: pad,
      boxSizing: "border-box", overflow: "hidden" }}>{children}</div>
  );
};
const Title: React.FC<{ t?: string }> = ({ t }) => t ? <div style={{ color: MUTED, fontSize: 42, fontWeight: 700 }}>{t}</div> : null;

const Counter: React.FC<{ s: Scene }> = ({ s }) => {
  const f = useCurrentFrame();
  const pop = useIn(46);
  const c = col(s.dir);
  const pts = s.dir === "up" ? [100, 92, 96, 82, 86, 70, 58, 62, 40, 28, 34, 12, 0] : [0, 8, 4, 18, 14, 30, 42, 38, 60, 72, 66, 88, 100];
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${10 + i * 61} ${20 + p * 1.9}`).join(" ");
  const draw = interpolate(f, [10, 70], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const from = s.dir === "down" ? 1.035 : s.dir === "up" ? 0.965 : 0.85;
  return (
    <Panel>
      <Title t={s.label} />
      <div style={{ color: "#fff", fontSize: (s.value || "").length > 9 ? 118 : 150, fontWeight: 900, letterSpacing: -3, lineHeight: 1.12, whiteSpace: "nowrap" }}>
        <Count value={s.value || ""} delay={6} from={from} />
      </div>
      {s.change ? <div style={{ display: "inline-block", marginTop: 6, background: c, color: s.dir === "none" ? "#111" : "#fff",
        fontSize: 54, fontWeight: 900, padding: "6px 26px", borderRadius: 14, transform: `scale(${0.6 + 0.4 * pop})`, opacity: pop }}>
        {arrow(s.dir)} {s.change.replace(/^[-+]/, "")}</div> : null}
      {s.dir === "up" || s.dir === "down" ? (
        <svg width={760} height={230} style={{ position: "absolute", left: 40, top: 420 }}>
          <path d={path} fill="none" stroke={c} strokeWidth={8} strokeLinejoin="round" strokeLinecap="round" pathLength={1} strokeDasharray={1} strokeDashoffset={draw} />
        </svg>) : null}
    </Panel>
  );
};

const Tile: React.FC<{ it: Item; delay: number; h: number }> = ({ it, delay, h }) => {
  const s = useIn(delay);
  const c = col(it.dir);
  return (
    <div style={{ width: 840, height: h, background: PANEL, borderRadius: 26, border: `2px solid ${LINE}`, display: "flex", alignItems: "center",
      padding: "0 40px", gap: 30, opacity: s, transform: `translateX(${(1 - s) * 120}px)`, boxSizing: "border-box" }}>
      <div style={{ width: 110, height: 110, borderRadius: 24, background: "rgba(255,214,10,0.12)", border: `2px solid ${LINE}`, flexShrink: 0,
        display: "flex", alignItems: "center", justifyContent: "center", color: Y, fontSize: 56, fontWeight: 900 }}>{it.icon || "•"}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ color: MUTED, fontSize: 34, fontWeight: 700, whiteSpace: "nowrap" }}>{it.label}</div>
        <div style={{ color: "#fff", fontSize: (it.value || "").length > 9 ? 62 : 78, fontWeight: 900, letterSpacing: -1, whiteSpace: "nowrap" }}>
          <Count value={it.value || ""} delay={delay + 2} from={0.9} dur={30} /></div>
      </div>
      {it.change ? <div style={{ color: c, fontSize: 46, fontWeight: 900, whiteSpace: "nowrap" }}>{arrow(it.dir)} {it.change.replace(/^[-+]/, "")}</div> : null}
    </div>
  );
};
const Tiles: React.FC<{ s: Scene }> = ({ s }) => {
  const { fps } = useVideoConfig();
  const items = (s.items || []).slice(0, 3);
  const h = items.length >= 3 ? 210 : 280;
  return (
    <AbsoluteFill style={{ alignItems: "center", paddingTop: s.title ? 120 : 140, gap: 28 }}>
      {s.title ? <div style={{ width: 840, color: MUTED, fontSize: 40, fontWeight: 700 }}>{s.title}</div> : null}
      {items.map((it, i) => <Tile key={i} it={it} h={h} delay={Math.max(2, Math.round((it.at ?? i * 1.2) * fps))} />)}
    </AbsoluteFill>
  );
};

const Bar: React.FC<{ it: Item; delay: number; max: number }> = ({ it, delay, max }) => {
  const f = useCurrentFrame();
  const t = interpolate(f, [delay, delay + 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const s = useIn(delay - 4);
  const c = col(it.dir);
  const pct = Math.abs(it.pct || 0);
  return (
    <div style={{ opacity: s, marginBottom: 50 }}>
      <div style={{ display: "flex", justifyContent: "space-between", color: "#fff", fontSize: 50, fontWeight: 800, marginBottom: 14 }}>
        <span style={{ whiteSpace: "nowrap" }}>{it.name}</span><span style={{ color: c, whiteSpace: "nowrap" }}>{arrow(it.dir)} <Count value={it.value || ""} delay={delay} from={0} dur={30} /></span>
      </div>
      <div style={{ height: 56, background: "rgba(255,255,255,0.08)", borderRadius: 28, overflow: "hidden" }}>
        <div style={{ width: `${Math.max(4, (pct / max) * 100) * t}%`, height: "100%", background: `linear-gradient(90deg, ${c}, ${c}AA)`, borderRadius: 28 }} />
      </div>
    </div>
  );
};
const Bars: React.FC<{ s: Scene }> = ({ s }) => {
  const { fps } = useVideoConfig();
  const items = (s.items || []).slice(0, 4);
  const max = Math.max(...items.map((i) => Math.abs(i.pct || 0)), 0.01) * 1.15;
  return (
    <Panel>
      <div style={{ color: MUTED, fontSize: 42, fontWeight: 700, marginBottom: items.length > 3 ? 36 : 60 }}>{s.title}</div>
      {items.map((it, i) => <Bar key={i} it={it} max={max} delay={Math.max(6, Math.round((it.at ?? i * 1.0) * fps))} />)}
    </Panel>
  );
};

const Gauge: React.FC<{ s: Scene }> = ({ s }) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sw = spring({ frame: f - 8, fps, config: { damping: 7, stiffness: 70 } });
  const lv = Math.min(1, Math.max(0, s.level ?? 0.85));
  const ang = -80 + (lv * 160) * sw;
  const badge = useIn(Math.round((s.at ?? 1.4) * fps));
  const flash = 0.75 + 0.25 * Math.sin(f / 3);
  const arc = (a0: number, a1: number) => {
    const r = 250, cx = 400, cy = 330;
    const p = (a: number) => [cx + r * Math.sin((a * Math.PI) / 180), cy - r * Math.cos((a * Math.PI) / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`;
  };
  return (
    <Panel pad="36px 52px">
      <Title t={s.label} />
      <svg width={840} height={420} viewBox="0 0 800 420" style={{ position: "absolute", top: 70, left: 0 }}>
        <path d={arc(-90, -30)} stroke="#3BD17A" strokeWidth={34} fill="none" />
        <path d={arc(-28, 28)} stroke={Y} strokeWidth={34} fill="none" />
        <path d={arc(30, 90)} stroke={UP} strokeWidth={34} fill="none" />
        <g transform={`rotate(${ang} 400 330)`}><line x1={400} y1={330} x2={400} y2={120} stroke="#fff" strokeWidth={14} strokeLinecap="round" /></g>
        <circle cx={400} cy={330} r={28} fill={Y} />
      </svg>
      <div style={{ position: "absolute", left: 0, right: 0, top: 445, textAlign: "center", color: "#fff", fontSize: 62, fontWeight: 900, whiteSpace: "nowrap" }}>{s.text}</div>
      {s.badge ? <div style={{ position: "absolute", left: "50%", top: 560, transform: `translateX(-50%) scale(${0.5 + 0.5 * badge})`, opacity: badge,
        background: UP, color: "#fff", fontSize: 44, fontWeight: 900, padding: "8px 30px", borderRadius: 14, whiteSpace: "nowrap",
        boxShadow: `0 0 ${30 * flash}px ${UP}` }}>⚠ {s.badge}</div> : null}
    </Panel>
  );
};

const Headline: React.FC<{ s: Scene }> = ({ s }) => {
  const f = useCurrentFrame();
  const s1 = useIn(0);
  const words = (s.text || "").split(" ");
  const shown = Math.floor(interpolate(f, [8, 8 + words.length * 4], [0, words.length], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
      <div style={{ width: 820, background: "#FAF8F2", borderRadius: 22, padding: "36px 46px 40px", boxSizing: "border-box",
        transform: `rotate(${(1 - s1) * -4}deg) scale(${0.85 + 0.15 * s1})`, opacity: s1, boxShadow: "0 18px 50px rgba(0,0,0,0.5)" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "3px solid #16161A", paddingBottom: 16 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14, fontSize: 40, fontWeight: 900, color: "#16161A" }}>
            <div style={{ width: 10, height: 44, background: "#E5322D" }} />{s.source}</div>
          <div style={{ fontSize: 30, color: "#6E6E76", fontWeight: 500 }}>{s.date}</div>
        </div>
        <div style={{ marginTop: 26, fontSize: 64, lineHeight: 1.3, fontWeight: 900, color: "#101014", wordBreak: "keep-all" }}>
          {words.map((w, i) => {
            const hot = w.includes("[") || w.includes("]");
            return <span key={i} style={{ opacity: i < shown ? 1 : 0.08, color: hot ? "#E5322D" : undefined }}>{w.replace(/[\[\]]/g, "")} </span>;
          })}
        </div>
        <div style={{ marginTop: 18, fontSize: 24, color: "#96969C", fontWeight: 600 }}>온라인 기사 헤드라인</div>
      </div>
    </AbsoluteFill>
  );
};

// 핵심 문구: [대괄호] 부분은 노랑 강조
const Point: React.FC<{ s: Scene }> = ({ s }) => {
  const s1 = useIn(2);
  const parts = (s.key || "").split(/(\[[^\]]+\])/).filter(Boolean);
  return (
    <Panel>
      <Title t={s.sub} />
      <div style={{ position: "absolute", left: 52, right: 52, top: 0, bottom: 0, display: "flex", alignItems: "center" }}>
        <div style={{ fontSize: (s.key || "").length > 22 ? 76 : 92, lineHeight: 1.28, fontWeight: 900, color: "#fff", wordBreak: "keep-all",
          transform: `translateY(${(1 - s1) * 30}px)`, opacity: s1 }}>
          {parts.map((p, i) => p.startsWith("[") ? <span key={i} style={{ color: Y }}>{p.slice(1, -1)}</span> : <span key={i}>{p}</span>)}
        </div>
      </div>
    </Panel>
  );
};

const Frame: React.FC<{ tag: string; idx: number; n: number }> = ({ tag, idx, n }) => {
  const f = useCurrentFrame();
  const glow = 0.55 + 0.25 * Math.sin(f / 9);
  const c = (st: React.CSSProperties) => ({ position: "absolute" as const, width: 34, height: 34, borderColor: Y, opacity: glow, ...st });
  return (
    <AbsoluteFill style={{ background: BG, fontFamily: font }}>
      <AbsoluteFill style={{ backgroundImage: "linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)", backgroundSize: "46px 46px" }} />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 55%, rgba(255,214,10,0.10), transparent 65%)" }} />
      <div style={c({ left: 22, top: 22, borderLeft: "4px solid", borderTop: "4px solid" })} />
      <div style={c({ right: 22, top: 22, borderRight: "4px solid", borderTop: "4px solid" })} />
      <div style={c({ left: 22, bottom: 22, borderLeft: "4px solid", borderBottom: "4px solid" })} />
      <div style={c({ right: 22, bottom: 22, borderRight: "4px solid", borderBottom: "4px solid" })} />
      <div style={{ position: "absolute", left: 64, top: 52, color: "rgba(255,255,255,0.7)", fontSize: 32, fontWeight: 700 }}>{tag}</div>
      <div style={{ position: "absolute", right: 64, top: 44, color: Y, fontSize: 30, fontWeight: 800, border: `2px solid ${LINE}`, borderRadius: 30, padding: "6px 22px" }}>
        {String(idx).padStart(2, "0")} / {String(n).padStart(2, "0")}</div>
    </AbsoluteFill>
  );
};

const Fade: React.FC<{ len: number; children: React.ReactNode }> = ({ len, children }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 6, len - 6, len], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ opacity: o, fontFamily: font, alignItems: "center", paddingTop: 130 }}>{children}</AbsoluteFill>;
};

const MAP: Record<string, React.FC<{ s: Scene }>> = { counter: Counter, tiles: Tiles, bars: Bars, gauge: Gauge, headline: Headline, point: Point };

export const Card: React.FC<CardProps> = ({ scenes, tag }) => {
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ background: BG }}>
      {scenes.map((sc, i) => {
        const C = MAP[sc.type] || Point;
        const from = Math.round(sc.from * fps);
        const len = Math.max(1, Math.round(sc.to * fps) - from);
        const full = sc.type === "tiles" || sc.type === "headline";
        return (
          <Sequence key={i} from={from} durationInFrames={len}>
            <Frame tag={tag} idx={i + 1} n={scenes.length} />
            {full ? <Fade len={len}><AbsoluteFill style={{ paddingTop: 0 }}><C s={sc} /></AbsoluteFill></Fade> : <Fade len={len}><C s={sc} /></Fade>}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
