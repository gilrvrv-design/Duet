"""Microphone input (spec §5.6 FR-H1, FR-H2): hear an acoustic piano while the bottles ring.

``MicListener`` takes audio in blocks, finds note attacks (spectral flux) and names the
note at each attack (harmonic sum over the piano range). Bottles are filtered out using
what the conductor already knows: when each one was struck (onset attribution) and what
it sounds like (spectral masking of its partials while it rings).

Suited to one pianist note at a time, which is what beginner parts are.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from duet.listening import PlayedNote, wait_for_pitches
from duet.pitch import midi_to_hz
from duet.profile import RobotProfile

FRAME = 2048  # pitch analysis window
ONSET_FRAME = 1024  # attack detection window: shorter, so attacks are found sooner
HOP = 256
ROBOT_WINDOW_US = 50_000  # an attack this close to a strike may be the bottle
MIN_GAP_US = 80_000  # two attacks closer than this are one note
MASK_SEMITONES = 0.6
SETTLE_S = 0.04  # a note is named this long after its attack, once the hammer noise fades
KEEP_S = 1.0  # audio kept behind the analysis point; older audio is dropped
REANCHOR_US = 20_000  # a block this far from where it should start means audio was lost
POLL_US = 10_000


@dataclass(frozen=True)
class RobotSound:
    t_us: int
    pitch: int


@dataclass
class MicListener:
    sr: int
    robot: RobotProfile | None = None
    piano_range: tuple[int, int] = (48, 84)  # C3..C6
    flux_threshold: float = 0.5  # relative to the loudest attack heard so far
    residual_ratio: float = 0.35  # what must remain after masking to count as piano
    robot_sounds: list[RobotSound] = field(default_factory=list)
    _buffer: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))
    _buffer_t0: int = 0
    _dropped: int = 0  # samples trimmed from the front; all positions are absolute
    _prev_mag: np.ndarray | None = None
    _frame_index: int = 0
    _flux_peak: float = 1e-9
    _floor: float | None = None
    _last_onset_us: int = -(10**12)
    _pending: list[int] = field(default_factory=list)  # onsets waiting for enough audio

    def expect_robot(self, sounds: list[RobotSound]) -> None:
        """Tell the listener when the robot will sound (from the conductor's plan)."""
        self.robot_sounds = sorted(sounds, key=lambda s: s.t_us)

    # streaming ----------------------------------------------------------------
    def feed(self, samples: np.ndarray, t0_us: int | None = None) -> list[PlayedNote]:
        """Add a block of mono samples starting at clock time ``t0_us``; return new notes."""
        if t0_us is not None:
            self._anchor(t0_us)
        self._buffer = np.concatenate([self._buffer, samples.astype(np.float32)])
        notes = []
        window = np.hanning(ONSET_FRAME)
        while (self._frame_index + 1) * HOP + ONSET_FRAME <= self._end:
            start = self._frame_index * HOP
            mag = np.abs(np.fft.rfft(self._audio(start, start + ONSET_FRAME) * window))
            if self._prev_mag is not None:
                flux = float(np.sum(np.maximum(0, np.log1p(mag) - np.log1p(self._prev_mag))))
                energy = float(np.sum(mag**2))
                louder = energy > 1.1 * float(np.sum(self._prev_mag**2))
                # Quietest level heard, rising slowly, so it tracks the room, not the music.
                # Compare first, then update, so an attack cannot raise its own bar.
                above_room = self._floor is None or energy > 10 * self._floor  # +10 dB
                quiet = max(energy, 1e-10)  # digital silence must not pin the floor at 0
                self._floor = quiet if self._floor is None else min(self._floor * 1.002, quiet)
                self._flux_peak = max(self._flux_peak * 0.9995, flux)
                t_us = self._time_of(start + ONSET_FRAME)
                if (
                    louder  # an attack gets louder; a cut-off or a fade does not
                    and above_room
                    and flux > self.flux_threshold * self._flux_peak
                    and flux > 5.0
                    and t_us - self._last_onset_us > MIN_GAP_US
                ):
                    self._last_onset_us = t_us
                    self._pending.append(self._attack_sample(start))
            self._prev_mag = mag
            self._frame_index += 1
            notes += self._resolve_pending()
        self._trim()
        return notes

    # buffer --------------------------------------------------------------------
    @property
    def _end(self) -> int:
        """Absolute position just after the last sample received."""
        return self._dropped + self._buffer.size

    def _audio(self, start: int, stop: int) -> np.ndarray:
        """Samples at absolute positions ``start``..``stop`` (what is still kept)."""
        return self._buffer[max(0, start - self._dropped) : max(0, stop - self._dropped)]

    def _anchor(self, t0_us: int) -> None:
        """Pin the clock to a block's start time: at the first block, and again whenever
        the source says a block starts somewhere else than where the audio got to (the
        driver dropped samples), so timing does not slip for the rest of the session."""
        if self._end == 0:
            self._buffer_t0 = t0_us
            return
        slip = t0_us - self._time_of(self._end)
        if abs(slip) > REANCHOR_US:
            self._buffer_t0 += slip

    def _trim(self) -> None:
        """Drop audio nothing will read again, so a long session uses constant memory."""
        keep = [self._frame_index * HOP - HOP] + [p - FRAME for p in self._pending]
        cut = min(keep) - round(KEEP_S * self.sr)
        if cut - self._dropped > 0:
            self._buffer = self._buffer[cut - self._dropped :].copy()
            self._dropped = cut

    def _attack_sample(self, frame_start: int) -> int:
        """Where in the window the attack really is: the first sample above half of the
        level the attack reaches (the window only says "somewhere in here")."""
        lo = max(0, frame_start - HOP)
        region = np.abs(self._audio(lo, frame_start + ONSET_FRAME + HOP))
        if region.size == 0:
            return frame_start
        before = float(np.percentile(region[:HOP], 90)) if region.size > HOP else 0.0
        peak = float(region.max())
        threshold = before + 0.5 * (peak - before)
        return lo + int(np.argmax(region >= threshold))

    def _time_of(self, sample: int) -> int:
        return self._buffer_t0 + round(sample / self.sr * 1_000_000)

    def _resolve_pending(self) -> list[PlayedNote]:
        """Name each attack once 40 ms of audio after it has arrived."""
        out, keep = [], []
        settle = int(SETTLE_S * self.sr)
        for start in self._pending:
            if start + settle + FRAME > self._end:
                keep.append(start)
                continue
            note = self._name_note(start)
            if note is not None:
                out.append(note)
        self._pending = keep
        return out

    # pitch --------------------------------------------------------------------
    def _name_note(self, start: int) -> PlayedNote | None:
        t_us = self._time_of(start)  # ``start`` is the attack sample
        settle = int(SETTLE_S * self.sr)
        segment = self._audio(start + settle, start + settle + FRAME)
        window = np.hanning(FRAME)
        after = np.abs(np.fft.rfft(segment * window, 4 * FRAME))
        before_audio = self._audio(max(0, start - FRAME), start)
        before = np.zeros_like(after)
        if before_audio.size == FRAME:
            before = np.abs(np.fft.rfft(before_audio * window, 4 * FRAME))
        # Only what is new at this attack: notes that were already ringing are not it.
        spectrum = np.maximum(0.0, after - before)
        freqs = np.fft.rfftfreq(4 * FRAME, 1 / self.sr)
        robot_struck = any(abs(s.t_us - t_us) <= ROBOT_WINDOW_US for s in self.robot_sounds)
        if robot_struck:
            # The new energy includes the bottle: mask its partials and see what is left.
            _, full = self._best_pitch(spectrum, freqs)
            pitch, residual = self._best_pitch(self._mask_ringing(spectrum, freqs, t_us), freqs)
            if residual < self.residual_ratio * full:
                return None  # the attack was only the bottle
        else:
            # Nothing was struck, so the new energy is all piano: bottles that were already
            # ringing are removed by the before/after difference, even on the same note.
            pitch, _ = self._best_pitch(spectrum, freqs)
        level = float(np.sqrt(np.mean(segment**2)))
        velocity = int(np.clip(30 + 97 * min(1.0, level / 0.3), 1, 127))
        return PlayedNote(t_us, pitch, velocity)

    def _best_pitch(self, spectrum, freqs) -> tuple[int, float]:
        def peak(hz: float) -> float:
            lo, hi = hz * 2 ** (-0.5 / 12), hz * 2 ** (0.5 / 12)
            band = spectrum[(freqs >= lo) & (freqs <= hi)]
            return float(band.max()) if band.size else 0.0

        best, best_salience = self.piano_range[0], 0.0
        for midi in range(self.piano_range[0], self.piano_range[1] + 1):
            f0 = midi_to_hz(midi)
            fundamental = peak(f0)
            # Harmonic sum; a candidate with almost nothing at its own fundamental is
            # discounted, which stops a note from being heard an octave too low.
            salience = fundamental + sum(peak(f0 * h) / h for h in (2, 3, 4, 5))
            if fundamental < 0.1 * spectrum.max():
                salience *= 0.5
            if salience > best_salience:
                best, best_salience = midi, salience
        # Octave check: the fundamental can be cancelled (for example by a ringing bottle
        # on the same note). If the note an octave down has its 3rd harmonic, which the
        # higher note cannot produce, the lower note is the one being played.
        lower = best - 12
        if lower >= self.piano_range[0]:
            f_low = midi_to_hz(lower)
            if peak(3 * f_low) >= 0.3 * peak(midi_to_hz(best)) and peak(5 * f_low) > 0:
                return lower, best_salience
        return best, best_salience

    def _mask_ringing(self, spectrum, freqs, t_us: int):
        spectrum = spectrum.copy()
        if self.robot is None:
            return spectrum
        ring_us = self.robot.sound.decay_ms * 1000
        for s in self.robot_sounds:
            if s.t_us - ROBOT_WINDOW_US <= t_us <= s.t_us + ring_us:  # struck or ringing
                bottle = self.robot.bottle_index(s.pitch)
                hz = self.robot.notes[bottle].hz if bottle is not None else midi_to_hz(s.pitch)
                for ratio in self.robot.sound.partials:
                    centre = hz * ratio
                    lo = centre * 2 ** (-MASK_SEMITONES / 12)
                    hi = centre * 2 ** (MASK_SEMITONES / 12)
                    spectrum[(freqs >= lo) & (freqs <= hi)] = 0.0
        return spectrum


@dataclass
class MicKeys:
    """A microphone as key input for wait and follow modes. ``source.read()`` returns
    (samples, t0_us) for audio that arrived since the last call (e.g. from sounddevice)."""

    listener: MicListener
    source: object
    timeout_s: float | None = None  # None: wait as long as it takes
    played: list[PlayedNote] = field(default_factory=list)

    def poll(self, clock) -> list[PlayedNote]:
        samples, t0 = self.source.read()
        new = self.listener.feed(samples, t0) if samples.size else []
        self.played += new
        return new

    def robot_strike(self, t_us: int, pitch: int) -> None:
        """The conductor calls this for every strike it sends."""
        self.listener.robot_sounds.append(RobotSound(t_us, pitch))

    def next_event_us(self, clock) -> int:
        return clock.now_us() + POLL_US

    def wait_for(self, pitches, since_us, clock) -> int:
        return wait_for_pitches(self, pitches, since_us, clock, self.timeout_s, POLL_US)


class SoundDeviceSource:
    """Live microphone through sounddevice (PortAudio): ``pip install sounddevice``.

    Blocks are stamped with the Hub clock when they arrive, minus their length, which
    is accurate to the audio driver's latency (a few ms; calibrate it like the strikes).
    Every read gives the first block's time, so the listener re-anchors after the driver
    drops audio; ``overflows`` counts the blocks PortAudio flagged.
    """

    def __init__(self, sr: int = 22050, device=None, block: int = 512) -> None:
        import queue

        import sounddevice

        from duet.device.clock import hub_now_us

        self._queue: queue.Queue = queue.Queue()
        self._now = hub_now_us
        self.overflows = 0

        def callback(indata, frames, _time, status):
            if status:
                self.overflows += 1
            self._queue.put((indata[:, 0].copy(), self._now() - round(frames / sr * 1e6)))

        self._stream = sounddevice.InputStream(
            samplerate=sr,
            channels=1,
            dtype="float32",
            blocksize=block,
            device=device,
            callback=callback,
        )
        self._stream.start()

    def read(self):
        blocks = []
        while not self._queue.empty():
            blocks.append(self._queue.get_nowait())
        if not blocks:
            return np.zeros(0, np.float32), None
        return np.concatenate([b for b, _ in blocks]), blocks[0][1]

    def close(self) -> None:
        self._stream.stop()
        self._stream.close()
