// Numbers shown in the video. Update from dataset/*.md after the final runs (single place to edit).
export const DATA = {
  runs: "1,624",
  videos: "384",
  solidFate: "30 / 31",          // solid burn-or-out cases predicted with each case left out (dataset/loo_eval.md)
  gasTime: "×1.42",              // data model: typical error of gas flame-out time (dataset/predict_eval.md)
  gasGuess: "×2.67",
};

// Voice-over (ElevenLabs, voice "Jesse - Animation Character, Friendly", take A, public/voice.mp3), one caption per scene.
// Scene boundaries sit in the pauses found with ffmpeg silencedetect.
export const CAPTIONS = [
  "Hi, I'm Ember! Moon bases will breathe 30% oxygen.",
  "But NASA has never burned a solid in microgravity above 22%.",
  "Flame in Freefall shows what's really been tested, for any cabin air.",
  "Our flame model is tuned on 384 NASA fire videos.",
  "Light anything: on the ISS, cutting the fans starves the fire.",
  "On the Moon, it doesn't.",
  "Every answer traces back to NASA.",
];
