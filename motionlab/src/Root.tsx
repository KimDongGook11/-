import React from "react";
import { Composition } from "remotion";
import { KospiTest, TOTAL } from "./KospiTest";

export const Root: React.FC = () => (
  <Composition id="KospiTest" component={KospiTest} durationInFrames={TOTAL} fps={30} width={920} height={860} />
);
