// Numbers shown in the video. Update from dataset/*.md after the final runs (single place to edit).
export const DATA = {
  runs: "1,624",
  videos: "384",
  solidFate: "30 / 31",          // solid burn-or-out cases predicted with each case left out (dataset/loo_eval.md)
  gasTime: "×1.42",              // data model: typical error of gas flame-out time (dataset/predict_eval.md)
  gasGuess: "×2.67",
};

// Voice-over script, one caption per scene (also the subtitle track; English subtitles are required).
export const CAPTIONS = [
  "Hi, I'm Ember! Moon bases will breathe 30% oxygen.",
  "But NASA has never burned a solid in microgravity above 22%.",
  "Flame in Freefall shows what NASA really tested, for any cabin air.",
  "Our flame model is tuned on 384 NASA videos and checked on test days it never saw.",
  "Click any object: does a fire keep burning? Do the fans matter?",
  "Every answer cites NASA. Flame in Freefall.",
];
