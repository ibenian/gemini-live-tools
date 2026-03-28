(function (global) {
    'use strict';

    // -----------------------------------------------------------------------
    // WavStreamParser — extracts complete WAV files from a chunked byte stream
    // -----------------------------------------------------------------------
    class WavStreamParser {
        constructor() { this._buf = new Uint8Array(0); }

        push(data) {
            const merged = new Uint8Array(this._buf.length + data.length);
            merged.set(this._buf);
            merged.set(data, this._buf.length);
            this._buf = merged;
            const wavs = [];
            let pos = 0;
            while (pos + 8 <= this._buf.length) {
                if (this._buf[pos] !== 0x52 || this._buf[pos + 1] !== 0x49 ||
                    this._buf[pos + 2] !== 0x46 || this._buf[pos + 3] !== 0x46) {
                    pos++; continue;
                }
                const riffPayload = new DataView(
                    this._buf.buffer, this._buf.byteOffset + pos + 4, 4
                ).getUint32(0, true);
                const total = riffPayload + 8;
                if (pos + total > this._buf.length) break;
                wavs.push(this._buf.buffer.slice(
                    this._buf.byteOffset + pos,
                    this._buf.byteOffset + pos + total
                ));
                pos += total;
            }
            this._buf = this._buf.slice(pos);
            return wavs;
        }
    }

    // -----------------------------------------------------------------------
    // TTSAudioPlayer — Web Audio playback with volume, limiter, gapless queue
    // -----------------------------------------------------------------------
    class TTSAudioPlayer {
        /**
         * @param {Object} opts
         * @param {number}   [opts.volume=0.5]        Initial volume (0–1)
         * @param {string}   [opts.persistKey='tts']   localStorage prefix (null to disable)
         * @param {Function} [opts.onStateChange]      Called with 'playing' | 'idle' | 'loading'
         * @param {Function} [opts.onVolumeChange]     Called with (volume, muted)
         */
        constructor(opts = {}) {
            this._persistKey = opts.persistKey ?? 'tts';
            this._onStateChange = opts.onStateChange || null;
            this._onVolumeChange = opts.onVolumeChange || null;

            this._ctx = null;
            this._gainNode = null;
            this._limiterNode = null;

            this._requestId = 0;
            this._abortController = null;
            this._activeSources = [];
            this._prevSources = [];
            this._scheduleEndTime = 0;
            this._state = 'idle'; // 'idle' | 'loading' | 'playing'

            // Restore persisted volume/mute
            const defaultVol = opts.volume ?? 0.5;
            if (this._persistKey) {
                const saved = localStorage.getItem(this._persistKey + 'Volume');
                const savedMute = localStorage.getItem(this._persistKey + 'Muted') === 'true';
                this._volume = saved !== null ? parseFloat(saved) : defaultVol;
                this._muted = savedMute;
            } else {
                this._volume = defaultVol;
                this._muted = false;
            }
        }

        // --- Audio context setup (lazy) -----------------------------------

        _ensureContext() {
            const Ctx = window.AudioContext || window.webkitAudioContext;
            if (!Ctx) return null;
            if (!this._ctx) {
                this._ctx = new Ctx();

                // Limiter: aggressive compressor to catch peaks before they clip
                this._limiterNode = this._ctx.createDynamicsCompressor();
                this._limiterNode.threshold.setValueAtTime(-3, 0);
                this._limiterNode.knee.setValueAtTime(0, 0);
                this._limiterNode.ratio.setValueAtTime(20, 0);
                this._limiterNode.attack.setValueAtTime(0.001, 0);
                this._limiterNode.release.setValueAtTime(0.05, 0);
                this._limiterNode.connect(this._ctx.destination);

                // Gain node for volume control
                this._gainNode = this._ctx.createGain();
                const initVol = this._muted ? 0 : this._volume;
                this._gainNode.gain.setValueAtTime(initVol, 0);
                this._gainNode.connect(this._limiterNode);
            }
            return this._ctx;
        }

        _outputNode() {
            return this._gainNode || this._ctx.destination;
        }

        // --- Volume control -----------------------------------------------

        getVolume() { return this._volume; }
        isMuted() { return this._muted; }

        setVolume(v) {
            v = Math.max(0, Math.min(1, v));
            this._volume = v;
            this._muted = v === 0;
            if (this._gainNode && this._ctx) {
                this._gainNode.gain.setValueAtTime(v, this._ctx.currentTime);
            }
            this._persist('Volume', v);
            this._persist('Muted', this._muted);
            if (this._onVolumeChange) this._onVolumeChange(v, this._muted);
        }

        toggleMute() {
            if (!this._muted) {
                this._muted = true;
                if (this._gainNode && this._ctx) {
                    this._gainNode.gain.setValueAtTime(0, this._ctx.currentTime);
                }
            } else {
                this._muted = false;
                const restoreVol = this._volume || 0.5;
                this._volume = restoreVol;
                if (this._gainNode && this._ctx) {
                    this._gainNode.gain.setValueAtTime(restoreVol, this._ctx.currentTime);
                }
                this._persist('Volume', restoreVol);
            }
            this._persist('Muted', this._muted);
            if (this._onVolumeChange) this._onVolumeChange(this._muted ? 0 : this._volume, this._muted);
        }

        _persist(key, value) {
            if (this._persistKey) {
                localStorage.setItem(this._persistKey + key, String(value));
            }
        }

        // --- Playback state -----------------------------------------------

        isPlaying() { return this._state !== 'idle'; }

        _setState(s) {
            if (s !== this._state) {
                this._state = s;
                if (this._onStateChange) this._onStateChange(s);
            }
        }

        // --- Stop / cancel ------------------------------------------------

        stop() {
            this._requestId++;
            if (this._abortController) {
                this._abortController.abort();
                this._abortController = null;
            }
            for (const src of [...this._prevSources, ...this._activeSources]) {
                try { src.stop(); } catch (_) {}
            }
            this._prevSources = [];
            this._activeSources = [];
            this._scheduleEndTime = 0;
            this._setState('idle');
            if (this._ctx && this._ctx.state === 'suspended') {
                this._ctx.resume().catch(() => {});
            }
        }

        // --- Recording export ---------------------------------------------

        getMediaStream() {
            if (!this._ctx || !this._limiterNode) return null;
            if (this._mediaStreamDest) return this._mediaStreamDest.stream;
            this._mediaStreamDest = this._ctx.createMediaStreamDestination();
            this._limiterNode.connect(this._mediaStreamDest);
            return this._mediaStreamDest.stream;
        }

        // --- Main playback entry point ------------------------------------

        /**
         * Play audio from a streaming fetch Response.
         * Auto-detects audio/pcm vs audio/wav from Content-Type.
         * @param {Response} response - A fetch Response with streaming body
         * @returns {Promise<void>}
         */
        async playStream(response) {
            const myId = ++this._requestId;

            // Abort previous fetch but keep old audio until new starts
            if (this._abortController) {
                this._abortController.abort();
                this._abortController = null;
            }
            for (const src of this._prevSources) { try { src.stop(); } catch (_) {} }
            this._prevSources = this._activeSources;
            this._activeSources = [];
            this._scheduleEndTime = 0;

            const ctx = this._ensureContext();
            if (!ctx) { this._prevSources = []; this._setState('idle'); return; }
            if (ctx.state === 'suspended') {
                try {
                    await ctx.resume();
                } catch (err) {
                    console.warn('Failed to resume audio context:', err);
                    this._setState('idle');
                    return;
                }
            }

            this._setState('loading');

            const contentType = (response.headers.get('Content-Type') || '').split(';')[0].trim();
            const isRealtime = contentType === 'audio/pcm';

            try {
                if (isRealtime) {
                    await this._playPCMStream(response, myId);
                } else {
                    await this._playWAVStream(response, myId);
                }
            } catch (err) {
                if (err.name !== 'AbortError') console.warn('TTS stream error:', err);
            } finally {
                if (this._requestId === myId) {
                    this._abortController = null;
                    this._waitForScheduledEnd(myId);
                }
            }
        }

        _waitForScheduledEnd(myId) {
            if (!this._ctx || !this._scheduleEndTime ||
                this._scheduleEndTime <= this._ctx.currentTime) {
                if (this._requestId === myId) this._setState('idle');
                return;
            }
            const remainingMs = (this._scheduleEndTime - this._ctx.currentTime) * 1000 + 50;
            setTimeout(() => {
                if (this._requestId === myId) this._setState('idle');
            }, remainingMs);
        }

        /**
         * Play audio from a streaming fetch Response, with an AbortController
         * that the caller can use and the player will also abort on stop().
         * @param {Response} response
         * @param {AbortController} abortController
         * @returns {Promise<void>}
         */
        async playStreamWithAbort(response, abortController) {
            // Abort previous controller before setting new one
            if (this._abortController) {
                this._abortController.abort();
            }
            this._abortController = abortController;

            const myId = ++this._requestId;

            for (const src of this._prevSources) { try { src.stop(); } catch (_) {} }
            this._prevSources = this._activeSources;
            this._activeSources = [];
            this._scheduleEndTime = 0;

            const ctx = this._ensureContext();
            if (!ctx) { this._prevSources = []; this._setState('idle'); return; }
            if (ctx.state === 'suspended') await ctx.resume();

            this._setState('loading');

            const contentType = (response.headers.get('Content-Type') || '').split(';')[0].trim();
            const isRealtime = contentType === 'audio/pcm';

            try {
                if (isRealtime) {
                    await this._playPCMStream(response, myId);
                } else {
                    await this._playWAVStream(response, myId);
                }
            } catch (err) {
                if (err.name !== 'AbortError') console.warn('TTS stream error:', err);
            } finally {
                if (this._requestId === myId) {
                    this._abortController = null;
                    this._waitForScheduledEnd(myId);
                }
            }
        }

        // --- PCM streaming ------------------------------------------------

        async _playPCMStream(response, myId) {
            const sampleRate = parseInt(response.headers.get('X-Audio-Sample-Rate') || '24000', 10);
            const reader = response.body.getReader();
            let pcmAccum = new Uint8Array(0);
            const scheduleBytes = sampleRate * 2 * 0.5; // 500ms of s16le mono
            const ctx = this._ctx;
            const nativeRate = ctx.sampleRate;
            const needsResample = sampleRate !== nativeRate;

            async function resample(float32) {
                if (!needsResample) return float32;
                const duration = float32.length / sampleRate;
                const outLen = Math.round(duration * nativeRate);
                const offline = new OfflineAudioContext(1, outLen, nativeRate);
                const buf = offline.createBuffer(1, float32.length, sampleRate);
                buf.getChannelData(0).set(float32);
                const src = offline.createBufferSource();
                src.buffer = buf;
                src.connect(offline.destination);
                src.start(0);
                const rendered = await offline.startRendering();
                return rendered.getChannelData(0);
            }

            function pcmToFloat32(pcmSlice, byteLen) {
                const samples = new Int16Array(pcmSlice.buffer, pcmSlice.byteOffset, byteLen / 2);
                const float32 = new Float32Array(samples.length);
                for (let i = 0; i < samples.length; i++) float32[i] = samples[i] / 32768;
                return float32;
            }

            const scheduleFloat32 = async (float32) => {
                const resampled = await resample(float32);
                const audioBuffer = ctx.createBuffer(1, resampled.length, nativeRate);
                audioBuffer.getChannelData(0).set(resampled);

                const source = ctx.createBufferSource();
                source.buffer = audioBuffer;
                source.connect(this._outputNode());

                const now = ctx.currentTime;
                const startAt = this._scheduleEndTime > now
                    ? this._scheduleEndTime
                    : now + 0.02;
                source.start(startAt);
                this._scheduleEndTime = startAt + audioBuffer.duration;

                if (this._prevSources.length > 0) {
                    for (const s of this._prevSources) { try { s.stop(startAt); } catch (_) {} }
                    this._prevSources = [];
                }

                this._activeSources.push(source);
                source.onended = () => {
                    const idx = this._activeSources.indexOf(source);
                    if (idx >= 0) this._activeSources.splice(idx, 1);
                };
            };

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done || this._requestId !== myId) break;

                    const merged = new Uint8Array(pcmAccum.length + value.length);
                    merged.set(pcmAccum);
                    merged.set(value, pcmAccum.length);
                    pcmAccum = merged;

                    while (pcmAccum.length >= scheduleBytes) {
                        const byteLen = Math.floor(scheduleBytes / 2) * 2;
                        if (byteLen === 0) break;
                        const pcmSlice = pcmAccum.slice(0, byteLen);
                        pcmAccum = pcmAccum.slice(byteLen);

                        const float32 = pcmToFloat32(pcmSlice, byteLen);

                        if (this._requestId !== myId || ctx.state === 'closed') return;
                        if (this._state === 'loading') this._setState('playing');

                        await scheduleFloat32(float32);
                        if (pcmAccum.length < scheduleBytes) break;
                    }
                }

                // Flush remaining
                if (pcmAccum.length >= 2 && this._requestId === myId) {
                    const byteLen = pcmAccum.length - (pcmAccum.length % 2);
                    const float32 = pcmToFloat32(pcmAccum.slice(0, byteLen), byteLen);
                    await scheduleFloat32(float32);
                }
            } finally {
                reader.releaseLock();
            }
        }

        // --- WAV streaming ------------------------------------------------

        async _playWAVStream(response, myId) {
            const parser = new WavStreamParser();
            const reader = response.body.getReader();
            const ctx = this._ctx;

            try {
                while (true) {
                    const { done, value } = await reader.read();
                    if (done || this._requestId !== myId) break;

                    for (const wavBuf of parser.push(value)) {
                        if (this._requestId !== myId) break;
                        let audioBuffer;
                        try { audioBuffer = await ctx.decodeAudioData(wavBuf); }
                        catch (e) { console.warn('TTS: decodeAudioData failed', e); continue; }

                        if (this._requestId !== myId || ctx.state === 'closed') return;
                        if (this._state === 'loading') this._setState('playing');

                        const source = ctx.createBufferSource();
                        source.buffer = audioBuffer;
                        source.connect(this._outputNode());

                        const now = ctx.currentTime;
                        const startAt = this._scheduleEndTime > now
                            ? this._scheduleEndTime
                            : now + 0.05;
                        source.start(startAt);
                        this._scheduleEndTime = startAt + audioBuffer.duration;

                        if (this._prevSources.length > 0) {
                            for (const s of this._prevSources) { try { s.stop(startAt); } catch (_) {} }
                            this._prevSources = [];
                        }

                        this._activeSources.push(source);
                        source.onended = () => {
                            const idx = this._activeSources.indexOf(source);
                            if (idx >= 0) this._activeSources.splice(idx, 1);
                        };
                    }
                }
            } finally {
                reader.releaseLock();
            }
        }
    }

    // -----------------------------------------------------------------------
    // Export
    // -----------------------------------------------------------------------
    const exports = { TTSAudioPlayer, WavStreamParser };

    if (typeof module !== 'undefined' && module.exports) {
        module.exports = exports;
    } else {
        global.GeminiTTSPlayer = exports;
    }

})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);
