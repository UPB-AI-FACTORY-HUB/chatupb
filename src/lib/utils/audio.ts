type AudioQueueEvent = 'stop' | 'empty-queue' | 'id-change';

interface AudioQueueStopDetail {
	event: AudioQueueEvent;
	id: string | null;
}

export type OnStoppedCallback = (detail: AudioQueueStopDetail) => void;

/**
 * Pick a browser speech-synthesis voice. Uses the configured voice when the
 * browser has it; otherwise falls back to a voice for `lang` (the UI language).
 * Without the fallback, a voice id the browser doesn't know (e.g. the default
 * `alloy`, an OpenAI voice) leaves the system default voice, often English.
 */
export const getSpeechSynthesisVoice = (
	voices: SpeechSynthesisVoice[],
	voiceId: string | undefined,
	lang: string | undefined
): SpeechSynthesisVoice | undefined => {
	const configured = voices.find((v) => v.voiceURI === voiceId);
	if (configured || !lang) return configured;

	const normalize = (l: string) => l.toLowerCase().replace('_', '-');
	const target = normalize(lang);
	const base = target.split('-')[0];

	return (
		voices.find((v) => normalize(v.lang) === target) ??
		voices.find((v) => normalize(v.lang).split('-')[0] === base)
	);
};

export class AudioQueue {
	private audio: HTMLAudioElement;
	private queue: string[] = [];
	private current: string | null = null;
	private readonly _onEnded = () => this.next();

	id: string | null = null;
	onStopped: OnStoppedCallback | null = null;

	constructor(audioElement: HTMLAudioElement) {
		this.audio = audioElement;
		this.audio.addEventListener('ended', this._onEnded);
	}

	setId(newId: string) {
		if (this.id === newId) return;

		this.#halt();
		this.id = newId;
		this.onStopped?.({ event: 'id-change', id: newId });
	}

	setPlaybackRate(rate: number) {
		this.audio.playbackRate = rate;
	}

	enqueue(url: string) {
		this.queue.push(url);

		// Auto-play if nothing is currently playing or loaded
		if (this.audio.paused && !this.current) {
			this.next();
		}
	}

	play() {
		if (!this.current && this.queue.length > 0) {
			this.next();
		} else {
			this.audio.play();
		}
	}

	next() {
		this.current = this.queue.shift() ?? null;

		if (this.current) {
			this.audio.src = this.current;
			this.audio.play();
		} else {
			this.#halt();
			this.onStopped?.({ event: 'empty-queue', id: this.id });
		}
	}

	stop() {
		this.#halt();
		this.onStopped?.({ event: 'stop', id: this.id });
	}

	destroy() {
		this.audio.removeEventListener('ended', this._onEnded);
		this.#halt();
		this.onStopped = null;
	}

	/**
	 * Pause audio and clear queue without firing onStopped.
	 * Callers that need the callback should invoke it themselves.
	 */
	#halt() {
		this.audio.pause();
		this.audio.currentTime = 0;
		this.audio.removeAttribute('src');
		this.audio.load();
		this.queue = [];
		this.current = null;
	}
}
