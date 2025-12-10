
let audioContext = null;

function initAudio() {
	if (!audioContext) {
		const AudioContext = window.AudioContext || window.webkitAudioContext;
		if (AudioContext) {
			audioContext = new AudioContext();
		}
	}
}

export function playSuccessSound() {
	try {
		initAudio();
		if (!audioContext) return;

		if (audioContext.state === 'suspended') {
			audioContext.resume().catch(() => {});
		}

		const oscillator = audioContext.createOscillator();
		const gainNode = audioContext.createGain();

		oscillator.type = 'sine';
		// A pleasant high pitch beep (e.g. 1000Hz)
		oscillator.frequency.setValueAtTime(1000, audioContext.currentTime);

		// Envelope to avoid clicking
		gainNode.gain.setValueAtTime(0, audioContext.currentTime);
		gainNode.gain.linearRampToValueAtTime(0.1, audioContext.currentTime + 0.01);
		gainNode.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + 0.15);

		oscillator.connect(gainNode);
		gainNode.connect(audioContext.destination);

		oscillator.start();
		oscillator.stop(audioContext.currentTime + 0.2);
	} catch (e) {
		console.error("Failed to play success sound", e);
	}
}

export function playErrorSound() {
	try {
		initAudio();
		if (!audioContext) return;

		if (audioContext.state === 'suspended') {
			audioContext.resume().catch(() => {});
		}

		const now = audioContext.currentTime;
		const oscillator = audioContext.createOscillator();
		const gainNode = audioContext.createGain();

		// Use sine wave for a smoother, less abrasive sound
		oscillator.type = 'sine';

		// Play a low "dun-dun" sound
		oscillator.frequency.setValueAtTime(200, now);
		oscillator.frequency.setValueAtTime(150, now + 0.15); // Drop pitch for second note

		// Envelope: Pulse twice
		gainNode.gain.setValueAtTime(0, now);
		gainNode.gain.linearRampToValueAtTime(0.2, now + 0.05);
		gainNode.gain.linearRampToValueAtTime(0.05, now + 0.1); // Dip volume
		gainNode.gain.linearRampToValueAtTime(0.2, now + 0.2);  // Rise again
		gainNode.gain.exponentialRampToValueAtTime(0.001, now + 0.4);

		oscillator.connect(gainNode);
		gainNode.connect(audioContext.destination);

		oscillator.start();
		oscillator.stop(now + 0.45);
	} catch (e) {
		console.error("Failed to play error sound", e);
	}
}
