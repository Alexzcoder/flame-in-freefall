import { Composition } from "remotion";
import { Demo, DURATION_S } from "./Demo";

export const RemotionRoot: React.FC = () => (
  <Composition id="Demo" component={Demo} durationInFrames={DURATION_S * 30 - 3} fps={30} width={1920} height={1080} />
);
