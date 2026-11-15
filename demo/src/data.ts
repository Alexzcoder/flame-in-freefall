// Numbers shown in the video. Update from dataset/*.md after the final runs (single place to edit).
export const DATA = {
  runs: "1,624",
  videos: "384",
  solidFate: "30 / 31",          // solid burn-or-out cases predicted with each case left out (dataset/loo_eval.md)
  gasTime: "×1.42",              // data model: typical error of gas flame-out time (dataset/predict_eval.md)
  gasGuess: "×2.67",
};

// Voice-over (ElevenLabs "Eve - Narrative & Audiobooks", public/voice_v2.mp3), Problem / Solution / Demo; one subtitle
// per scene (written to out/flame-in-freefall-demo.srt for YouTube, not burned into the video).
export const CAPTIONS = [
  "Hi, I'm Ember! Moon bases will breathe 30% oxygen.",
  "But NASA has never burned a solid in microgravity above 22%.",
  "Flame in Freefall turns NASA's scattered fire data into checked, cited answers.",
  "Set any cabin air.",
  "Watch the flame change,",
  "checked against NASA fire videos.",
  "Light anything: on the ISS, cutting the fans starves it.",
  "On the Moon, it doesn't.",
  "Every answer traces back to NASA.",
];
