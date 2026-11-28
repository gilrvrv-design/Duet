"""Live practice on a real rig (docs/design/esp-first.md, step 6): the Hub plays a duet
on the rig while it listens to the pianist, and can be stopped at any moment.

Modes: "play" (the bot plays in time, nobody is listened to), "wait" (the bot waits for
each of the pianist's notes) and "follow" (the bot keeps the pianist's tempo). Every wait
in a performance goes through its clock, so a ``StoppableClock`` stops it cleanly; the
rig is then told to stop, which clears what it has queued (protocol 5).
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from duet.conductor import Performance, RealClock, one_rig, perform
from duet.device.gateway import DeviceFault, DeviceGateway, DeviceMismatch
from duet.listening import KeyInput, grade
from duet.performers import Instruments
from duet.profile import RobotProfile
from duet.score import DuetScore

MODES = ("play", "wait", "follow")
RING_OUT_US = 1_000_000  # after the last command is sent, the last notes still sound


class Stopped(Exception):
    """The performance was stopped before its end."""


class StoppableClock(RealClock):
    """The Hub's clock; once stopped, any wait on it raises Stopped."""

    def __init__(self) -> None:
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def sleep_until(self, t_us: int) -> None:
        if self._stop.wait(max(0.0, (t_us - self.now_us()) / 1_000_000)):
            raise Stopped


def play_live(
    score: DuetScore,
    url: str,
    robot: RobotProfile,
    instruments: Instruments,
    *,
    mode: str,
    keys: KeyInput | None,
    clock: StoppableClock,
    on_connect=lambda gateway: None,
) -> Performance:
    """Play ``score`` on the rig at ``url`` in ``mode``, hearing the pianist through ``keys``
    (wait and follow modes need them). Stopped through ``clock``, or by Ctrl-C, it stops
    the rig too and raises."""
    if mode not in MODES:
        raise ValueError(f"mode {mode!r}: choose one of {', '.join(MODES)}")
    if mode != "play" and keys is None:
        raise ValueError(f"{mode} mode listens to the pianist: give a key input")
    with DeviceGateway(url, profile=robot) as gateway:
        on_connect(gateway)
        try:
            perf = perform(
                score,
                one_rig(score, [gateway]),
                clock,
                instruments=instruments,
                keys=None if mode == "play" else keys,
                mode="wait" if mode == "play" else mode,
            )
            gateway.wait_acked()
            clock.sleep_until(clock.now_us() + RING_OUT_US)
        except (Stopped, KeyboardInterrupt):
            gateway.stop()  # the rig clears what it has queued and goes quiet
            raise
    return perf


def summary(perf: Performance, mode: str) -> str:
    """How it went, for the pianist: how long the bot waited or how it followed, and the
    grade of what was heard."""
    if mode == "play":
        return f"played {perf.messages_sent} commands"
    pace = (
        f"waited {perf.waited_us / 1e6:.1f} s for you"
        if mode == "wait"
        else f"followed you: tempo now {100 / perf.final_rate:.0f}% of written"
    )
    return f"{pace}\n{grade(perf.expected_pianist(), perf.played).feedback()}"


# Live sessions on a server ---------------------------------------------------------
# The rig's page asks a server to run a practice (docs/device-api.md, "Practice"): the
# server listens to the pianist through an input on its own machine, a MIDI keyboard or
# a microphone, and drives the rig over its link.

KeyInputs = Mapping[str, Callable[[RobotProfile], KeyInput]]  # name -> opens it


def machine_inputs() -> dict[str, Callable[[RobotProfile], KeyInput]]:
    """What this machine can hear the pianist with: each MIDI input port, and the
    microphone where sounddevice is installed. Neither may be there; then there is none."""
    inputs: dict[str, Callable[[RobotProfile], KeyInput]] = {}
    try:
        import mido

        names = mido.get_input_names()
    except ImportError:  # no MIDI backend installed
        names = []
    for name in names:
        inputs[f"MIDI: {name}"] = lambda _robot, name=name: _midi_keys(name)
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        pass
    else:
        inputs["Microphone"] = _mic_keys
    return inputs


def _midi_keys(port: str) -> KeyInput:
    import mido

    from duet.listening import MidiKeys

    return MidiKeys(mido.open_input(port))


def _mic_keys(robot: RobotProfile) -> KeyInput:
    from duet.mic import MicKeys, MicListener, SoundDeviceSource

    return MicKeys(MicListener(22050, robot=robot), SoundDeviceSource())


class LiveError(Exception):
    """A practice that cannot start: the server is busy with one, or the request is wrong."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass
class Practice:
    """One practice on a rig, as the page sees it."""

    id: str
    title: str
    mode: str
    rig: str  # the rig's link, ws://... or tcp://...
    state: str = "connecting"  # then "playing"; at the end "done", "stopped" or "failed"
    detail: str = ""  # at the end: how it went, or why it failed
    clock: StoppableClock = field(default_factory=StoppableClock, repr=False)

    @property
    def over(self) -> bool:
        return self.state in ("done", "stopped", "failed")

    def view(self) -> dict:
        keep = ("id", "title", "mode", "rig", "state", "detail")
        return {k: getattr(self, k) for k in keep}


class Practices:
    """The server's practices: one at a time, as a rig takes one Hub at a time."""

    def __init__(self, inputs: KeyInputs) -> None:
        self.inputs = inputs
        self._lock = threading.Lock()
        self._all: dict[str, Practice] = {}
        self._threads: list[threading.Thread] = []

    def start(
        self,
        score: DuetScore,
        rig: str,
        robot: RobotProfile,
        instruments: Instruments,
        mode: str,
        input_name: str | None,
    ) -> Practice:
        if mode not in MODES:
            raise LiveError("LIVE_INVALID", f"mode {mode!r}: choose one of {', '.join(MODES)}")
        if mode != "play" and input_name not in self.inputs:
            offered = ", ".join(self.inputs) or "none on this server"
            raise LiveError("LIVE_INVALID", f"{mode} mode needs an input (offered: {offered})")
        with self._lock:
            busy = next((p for p in self._all.values() if not p.over), None)
            if busy is not None:
                raise LiveError("PRACTICE_BUSY", f"{busy.title!r} is playing on {busy.rig}")
            practice = Practice(uuid.uuid4().hex[:12], score.meta.title, mode, rig)
            self._all[practice.id] = practice
        keys = None if mode == "play" else self.inputs[input_name](robot)
        thread = threading.Thread(
            target=self._run,
            args=(practice, score, robot, instruments, keys),
            name=f"practice-{practice.id}",
            daemon=True,
        )
        self._threads.append(thread)
        thread.start()
        return practice

    def _run(self, practice, score, robot, instruments, keys) -> None:
        def connected(_gateway) -> None:
            practice.state = "playing"

        try:
            perf = play_live(
                score, practice.rig, robot, instruments,
                mode=practice.mode, keys=keys, clock=practice.clock, on_connect=connected,
            )  # fmt: skip
        except Stopped:
            practice.state, practice.detail = "stopped", "stopped before the end"
        except (OSError, ConnectionError, TimeoutError, DeviceFault, DeviceMismatch) as exc:
            # The rig is the outside world: it may be off, busy with another Hub, or say no.
            practice.state, practice.detail = "failed", f"the rig at {practice.rig}: {exc}"
        except BaseException as exc:  # a bug: say so, and still free the server for the next
            practice.state, practice.detail = "failed", f"internal error: {exc!r}"
            raise
        else:
            practice.state, practice.detail = "done", summary(perf, practice.mode)

    def get(self, practice_id: str) -> Practice:
        return self._all[practice_id]

    def stop(self, practice_id: str) -> Practice:
        practice = self._all[practice_id]
        practice.clock.stop()
        return practice

    def shutdown(self) -> None:
        for practice in self._all.values():
            practice.clock.stop()
        for thread in self._threads:
            thread.join(timeout=10)
