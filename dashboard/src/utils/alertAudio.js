// Web Audio API context for high-tech security alert chime
let audioCtx = null;

/**
 * Play a professional tactical security alert chime
 * @param {boolean} isIntrusion
 */
export function playAlertChime(isIntrusion = true) {
  try {
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextClass) return;
    if (!audioCtx) {
      audioCtx = new AudioContextClass();
    }
    if (audioCtx.state === 'suspended') {
      audioCtx.resume();
    }

    const now = audioCtx.currentTime;

    if (isIntrusion) {
      // 2-tone professional tactical alert chime (740Hz -> 880Hz / 1108Hz)
      const osc1 = audioCtx.createOscillator();
      const gain1 = audioCtx.createGain();
      osc1.type = 'sine';
      osc1.frequency.setValueAtTime(740, now);
      osc1.frequency.exponentialRampToValueAtTime(880, now + 0.12);
      gain1.gain.setValueAtTime(0.22, now);
      gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.35);

      osc1.connect(gain1);
      gain1.connect(audioCtx.destination);
      osc1.start(now);
      osc1.stop(now + 0.35);

      const osc2 = audioCtx.createOscillator();
      const gain2 = audioCtx.createGain();
      osc2.type = 'sine';
      osc2.frequency.setValueAtTime(1108.73, now + 0.12);
      gain2.gain.setValueAtTime(0.18, now + 0.12);
      gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.45);

      osc2.connect(gain2);
      gain2.connect(audioCtx.destination);
      osc2.start(now + 0.12);
      osc2.stop(now + 0.45);
    } else {
      // Subtle notice chime
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, now);
      gain.gain.setValueAtTime(0.12, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start(now);
      osc.stop(now + 0.25);
    }
  } catch {
    // Graceful fallback if AudioContext is blocked by browser policy
  }
}

/**
 * Speak out an alert in a professional authoritative security tone
 * @param {string} text The text to speak
 */
export function speakAlert(text) {
  if (typeof window === 'undefined' || !window.speechSynthesis) return;

  try {
    // Cancel previous ongoing speech to prevent overlapping or lagging queues
    window.speechSynthesis.cancel();

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95; // Calm, deliberate, authoritative tone
    utterance.pitch = 1.0; // Steady professional pitch
    utterance.volume = 1.0;
    utterance.lang = 'en-US';

    const assignVoice = () => {
      const voices = window.speechSynthesis.getVoices();
      if (!voices || voices.length === 0) return;

      // Select highest quality English dispatch voice available
      const preferred = voices.find(
        (v) =>
          v.lang.startsWith('en') &&
          (v.name.includes('Natural') ||
            v.name.includes('Google') ||
            v.name.includes('Samantha') ||
            v.name.includes('Daniel') ||
            v.name.includes('Karen') ||
            v.name.includes('Alex'))
      ) || voices.find((v) => v.lang.startsWith('en'));

      if (preferred) {
        utterance.voice = preferred;
      }
    };

    if (window.speechSynthesis.getVoices().length > 0) {
      assignVoice();
    } else {
      window.speechSynthesis.onvoiceschanged = assignVoice;
    }

    // Small timeout to allow alert chime to lead before speech begins
    setTimeout(() => {
      window.speechSynthesis.speak(utterance);
    }, 240);
  } catch (err) {
    console.warn('Speech synthesis alert failed:', err);
  }
}
