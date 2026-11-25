// 시험: 기존 A안 레이아웃의 가운데 카드(920×860) 안을 채우는 모션 그래픽
// 우리 색: 검정·남색 바탕, 노랑 #FFD60A, 빨강 #FF4D5A, 파랑 #4D8DFF, 글꼴 Pretendard
import React from "react";
import "pretendard/dist/web/static/pretendard.css";
import { AbsoluteFill, Sequence, interpolate, spring, useCurrentFrame, useVideoConfig, Easing } from "remotion";

const Y = "#FFD60A", R = "#FF4D5A", B = "#4D8DFF", BG = "#0A0E18", PANEL = "#121A2B", LINE = "rgba(255,214,10,0.35)";
const font = "Pretendard, 'Pretendard Variable', sans-serif";
const fps = 30;
const S = (sec: number) => Math.round(sec * fps);
// 장면 경계 (영상 1.3초부터 시작하는 상대 시간, 초) — 멘트 문장 경계에 맞춤
export const SCENES = [
  { from: 0, to: 5.4 },     // 코스피 3.31% 급락, 4,708.53
  { from: 5.4, to: 10.4 },  // 장중 5% 넘게, 매도 사이드카
  { from: 10.4, to: 19.6 }, // 코스닥 635.49, 환율 1,343.7원
  { from: 19.6, to: 23.9 }, // 삼성전자 -3.06%, SK하이닉스 -2.52%
];
export const TOTAL = S(23.9);

const fmt = (v: number, d: number) => v.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

const Frame: React.FC<{ label: string; idx: number }> = ({ label, idx }) => {
  const f = useCurrentFrame();
  const glow = 0.55 + 0.25 * Math.sin(f / 9);
  const c = (s: React.CSSProperties) => ({ position: "absolute" as const, width: 34, height: 34, borderColor: Y, ...s });
  return (
    <AbsoluteFill style={{ background: BG, fontFamily: font }}>
      {/* 격자 */}
      <AbsoluteFill style={{
        backgroundImage: `linear-gradient(rgba(255,255,255,0.045) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.045) 1px, transparent 1px)`,
        backgroundSize: "46px 46px",
      }} />
      <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 55%, rgba(255,214,10,0.10), transparent 65%)" }} />
      {/* 모서리 표시 */}
      <div style={c({ left: 22, top: 22, borderLeft: "4px solid", borderTop: "4px solid", opacity: glow })} />
      <div style={c({ right: 22, top: 22, borderRight: "4px solid", borderTop: "4px solid", opacity: glow })} />
      <div style={c({ left: 22, bottom: 22, borderLeft: "4px solid", borderBottom: "4px solid", opacity: glow })} />
      <div style={c({ right: 22, bottom: 22, borderRight: "4px solid", borderBottom: "4px solid", opacity: glow })} />
      {/* 위 정보 줄 */}
      <div style={{ position: "absolute", left: 64, top: 52, color: "rgba(255,255,255,0.7)", fontSize: 30, fontWeight: 700, letterSpacing: 1 }}>
        오늘의 원픽 · {label}
      </div>
      <div style={{ position: "absolute", right: 64, top: 44, color: Y, fontSize: 30, fontWeight: 800, border: `2px solid ${LINE}`,
        borderRadius: 30, padding: "6px 22px" }}>
        {String(idx).padStart(2, "0")} / {String(SCENES.length).padStart(2, "0")}
      </div>
    </AbsoluteFill>
  );
};

const useIn = (delay = 0) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: f - delay, fps, config: { damping: 14, stiffness: 120 } });
};

const Fade: React.FC<{ len: number; children: React.ReactNode }> = ({ len, children }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 8, len - 8, len], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <AbsoluteFill style={{ opacity: o }}>{children}</AbsoluteFill>;
};

// 장면 1: 코스피 종가 카운터 + 하락 선 그래프
const CounterScene: React.FC = () => {
  const f = useCurrentFrame();
  const t = interpolate(f, [6, 54], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const val = 4869.7 + (4708.53 - 4869.7) * t;
  const pct = -3.31 * t;
  const pop = useIn(50);
  const pts = [0, 8, 4, 18, 14, 30, 42, 38, 60, 72, 66, 88, 100];
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${60 + i * 58} ${150 + p * 1.6}`).join(" ");
  const draw = interpolate(f, [10, 70], [1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const enter = useIn(0);
  return (
    <AbsoluteFill style={{ fontFamily: font, alignItems: "center", paddingTop: 150 }}>
      <div style={{ width: 800, height: 600, background: PANEL, borderRadius: 28, border: `2px solid ${LINE}`,
        boxShadow: `0 0 40px rgba(255,214,10,0.12)`, transform: `translateY(${(1 - enter) * 60}px)`, opacity: enter, padding: "38px 50px" }}>
        <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 36, fontWeight: 700 }}>코스피 종가</div>
        <div style={{ display: "flex", alignItems: "baseline", gap: 22, marginTop: 6 }}>
          <div style={{ color: "#fff", fontSize: 124, fontWeight: 900, letterSpacing: -2 }}>{fmt(val, 2)}</div>
        </div>
        <div style={{ display: "inline-block", marginTop: 4, background: R, color: "#fff", fontSize: 44, fontWeight: 900,
          padding: "6px 22px", borderRadius: 14, transform: `scale(${0.6 + 0.4 * pop})`, opacity: pop }}>
          ▼ {Math.abs(pct).toFixed(2)}%
        </div>
        <svg width={800} height={330} style={{ position: "absolute", left: 60, top: 400 }}>
          <path d={path} fill="none" stroke={R} strokeWidth={8} strokeLinejoin="round" strokeLinecap="round"
            pathLength={1} strokeDasharray={1} strokeDashoffset={draw} />
        </svg>
      </div>
    </AbsoluteFill>
  );
};

// 장면 2: 위험 계기판 + 매도 사이드카 배지
const GaugeScene: React.FC = () => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const sw = spring({ frame: f - 8, fps, config: { damping: 7, stiffness: 70 } });
  const ang = -80 + 155 * sw;                  // -80°(안정) → 75°(위험)
  const flash = f > 45 ? 0.75 + 0.25 * Math.sin(f / 3) : 0;
  const badge = useIn(42);
  const enter = useIn(0);
  const arc = (a0: number, a1: number) => {
    const r = 230, cx = 400, cy = 400;
    const p = (a: number) => [cx + r * Math.sin((a * Math.PI) / 180), cy - r * Math.cos((a * Math.PI) / 180)];
    const [x0, y0] = p(a0), [x1, y1] = p(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`;
  };
  return (
    <AbsoluteFill style={{ fontFamily: font, alignItems: "center", paddingTop: 150 }}>
      <div style={{ width: 800, height: 600, background: PANEL, borderRadius: 28, border: `2px solid ${LINE}`, opacity: enter,
        transform: `scale(${0.92 + 0.08 * enter})`, position: "relative" }}>
        <div style={{ position: "absolute", left: 50, top: 36, color: "rgba(255,255,255,0.75)", fontSize: 36, fontWeight: 700 }}>장중 하락 폭</div>
        <svg width={800} height={470} style={{ position: "absolute", top: 70 }}>
          <path d={arc(-90, -30)} stroke="#3BD17A" strokeWidth={34} fill="none" />
          <path d={arc(-28, 28)} stroke={Y} strokeWidth={34} fill="none" />
          <path d={arc(30, 90)} stroke={R} strokeWidth={34} fill="none" />
          <g transform={`rotate(${ang} 400 400)`}>
            <line x1={400} y1={400} x2={400} y2={210} stroke="#fff" strokeWidth={12} strokeLinecap="round" />
          </g>
          <circle cx={400} cy={400} r={26} fill={Y} />
        </svg>
        <div style={{ position: "absolute", left: 0, right: 0, top: 420, textAlign: "center", color: "#fff", fontSize: 60, fontWeight: 900 }}>
          장중 <span style={{ color: R }}>-5% 이상</span>
        </div>
        <div style={{ position: "absolute", left: "50%", top: 505, transform: `translateX(-50%) scale(${0.5 + 0.5 * badge})`, opacity: badge,
          background: R, color: "#fff", fontSize: 40, fontWeight: 900, padding: "8px 28px", borderRadius: 14,
          boxShadow: `0 0 ${30 * flash}px ${R}` }}>
          ⚠ 매도 사이드카 발동
        </div>
      </div>
    </AbsoluteFill>
  );
};

// 장면 3: 코스닥·환율 두 타일
const Tile: React.FC<{ delay: number; title: string; value: string; change: string; up: boolean; icon: string }> =
  ({ delay, title, value, change, up, icon }) => {
    const s = useIn(delay);
    return (
      <div style={{ width: 800, height: 260, background: PANEL, borderRadius: 26, border: `2px solid ${LINE}`, display: "flex",
        alignItems: "center", padding: "0 44px", gap: 34, opacity: s, transform: `translateX(${(1 - s) * 120}px)` }}>
        <div style={{ width: 120, height: 120, borderRadius: 26, background: "rgba(255,214,10,0.12)", border: `2px solid ${LINE}`,
          display: "flex", alignItems: "center", justifyContent: "center", color: Y, fontSize: 64, fontWeight: 900 }}>{icon}</div>
        <div style={{ flex: 1 }}>
          <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 34, fontWeight: 700 }}>{title}</div>
          <div style={{ color: "#fff", fontSize: 80, fontWeight: 900, letterSpacing: -1 }}>{value}</div>
        </div>
        <div style={{ color: up ? R : B, fontSize: 46, fontWeight: 900, textAlign: "right" }}>{up ? "▲" : "▼"} {change}</div>
      </div>
    );
  };
const TilesScene: React.FC = () => (
  <AbsoluteFill style={{ fontFamily: font, alignItems: "center", paddingTop: 170, gap: 40 }}>
    <Tile delay={4} title="코스닥" value="635.49" change="1.58%" up={false} icon="Q" />
    <Tile delay={S(4.6)} title="원/달러 환율" value="1,343.7원" change="8.9원" up={true} icon="₩" />
  </AbsoluteFill>
);

// 장면 4: 대형주 하락률 막대
const Bar: React.FC<{ delay: number; name: string; pct: number }> = ({ delay, name, pct }) => {
  const f = useCurrentFrame();
  const t = interpolate(f, [delay, delay + 30], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  const s = useIn(delay - 4);
  return (
    <div style={{ opacity: s, marginBottom: 46 }}>
      <div style={{ display: "flex", justifyContent: "space-between", color: "#fff", fontSize: 44, fontWeight: 800, marginBottom: 14 }}>
        <span>{name}</span><span style={{ color: B }}>▼ {(pct * t).toFixed(2)}%</span>
      </div>
      <div style={{ height: 46, background: "rgba(255,255,255,0.08)", borderRadius: 23, overflow: "hidden" }}>
        <div style={{ width: `${(pct / 3.5) * 100 * t}%`, height: "100%", background: `linear-gradient(90deg, ${B}, #8FB6FF)`, borderRadius: 23 }} />
      </div>
    </div>
  );
};
const BarsScene: React.FC = () => {
  const enter = useIn(0);
  return (
    <AbsoluteFill style={{ fontFamily: font, alignItems: "center", paddingTop: 150 }}>
      <div style={{ width: 800, height: 600, background: PANEL, borderRadius: 28, border: `2px solid ${LINE}`, opacity: enter, padding: "40px 52px" }}>
        <div style={{ color: "rgba(255,255,255,0.75)", fontSize: 36, fontWeight: 700, marginBottom: 50 }}>대형주 하락률 (오늘)</div>
        <Bar delay={8} name="삼성전자" pct={3.06} />
        <Bar delay={S(2.0)} name="SK하이닉스" pct={2.52} />
      </div>
    </AbsoluteFill>
  );
};

export const KospiTest: React.FC = () => {
  const comps = [CounterScene, GaugeScene, TilesScene, BarsScene];
  const labels = ["코스피 마감", "장중 충격", "코스닥·환율", "대형주"];
  return (
    <AbsoluteFill>
      {SCENES.map((sc, i) => {
        const C = comps[i];
        const len = S(sc.to) - S(sc.from);
        return (
          <Sequence key={i} from={S(sc.from)} durationInFrames={len}>
            <Frame label={labels[i]} idx={i + 1} />
            <Fade len={len}><C /></Fade>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
