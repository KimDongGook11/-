import React from "react";
import { Composition } from "remotion";
import { KospiTest, TOTAL } from "./KospiTest";
import { Card, CardProps } from "./Card";

const sample: CardProps = { tag: "국내 증시 마감", total: 6, scenes: [{ type: "point", from: 0, to: 6, key: "시험 [장면]", sub: "시험" }] };

export const Root: React.FC = () => (
  <>
    <Composition id="KospiTest" component={KospiTest} durationInFrames={TOTAL} fps={30} width={920} height={860} />
    <Composition id="Card" component={Card as any} durationInFrames={180} fps={30} width={920} height={860} defaultProps={sample}
      calculateMetadata={({ props }) => ({ durationInFrames: Math.max(30, Math.ceil(((props as any).total || 6) * 30)) })} />
  </>
);
