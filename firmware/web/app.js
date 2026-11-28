// The Duet web app, served by the device itself (docs/device-api.md). Plain JavaScript,
// no build step: what is here is what the board serves.
"use strict";

const POLL_MS = 1000;

// What each feature and channel means to a person; a board reports which it has.
const FEATURES = {
  wifi: ["Wi-Fi link to the Hub", "No Wi-Fi: the Hub connects over USB serial"],
  flash: ["Songs stay stored when the power is off", "Songs are kept in memory and lost at power-off"],
  play_button: ["A play button on the rig", "No play button: play songs from this page"],
  estop_button: ["A hardware emergency stop", "No hardware emergency stop: use the button on this page"],
};
const CHANNELS = {
  carriage_striker: () => "A bot plays the bottles (carriage and striker)",
  led_strip: (c) => `Lights show the pianist's keys (${c.count} LEDs)`,
  midi_out: () => "A bot plays a digital piano over MIDI",
};

const $ = (id) => document.getElementById(id);
let shown = { state: null, songs: null };

async function api(method, path) {
  const reply = await fetch(path, { method });
  const body = await reply.json();
  if (!reply.ok) throw new Error(body.error);
  return body;
}

function say(text) {
  $("message").textContent = text;
  $("message").hidden = !text;
}

// Run a command from a button, and show why if the device refuses it.
async function command(path) {
  try {
    await api("POST", path);
    say("");
  } catch (refused) {
    say(`The rig refused: ${refused.message}.`);
  }
  await refresh();
}

function showState(info) {
  const pill = $("state");
  const playing = info.state !== "idle";
  if (info.estopped) {
    pill.dataset.state = "estop";
    pill.textContent = "Emergency stop";
  } else {
    pill.dataset.state = info.state;
    pill.textContent = {
      idle: "Ready",
      homing: `Homing for slot ${info.slot}`,
      playing: `Playing slot ${info.slot}`,
    }[info.state];
  }
  $("stop").hidden = !playing;
  for (const li of $("songs").children) {
    const here = playing && Number(li.dataset.slot) === info.slot;
    li.toggleAttribute("data-playing", here);
    li.querySelector("button").disabled = playing || info.estopped;
  }
}

function showSongs(songs) {
  const list = $("songs");
  list.replaceChildren(
    ...songs.map(({ slot }) => {
      const li = document.createElement("li");
      li.dataset.slot = slot;
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = `Song in slot ${slot}`;
      const play = document.createElement("button");
      play.type = "button";
      play.className = "secondary";
      play.textContent = "Play";
      play.setAttribute("aria-label", `Play slot ${slot}`);
      play.addEventListener("click", () => command(`/api/songs/${slot}/play`));
      li.append(name, play);
      return li;
    }),
  );
  $("no-songs").hidden = songs.length > 0;
}

function showBoard(info) {
  const { hello, channels } = info;
  $("device").textContent = `${hello.device_id} · ${hello.board}`;
  const items = [
    ...channels.map((c) => [true, CHANNELS[c.kind](c)]),
    ...Object.entries(FEATURES).map(([name, [has, lacks]]) => {
      const present = hello.features.includes(name);
      return [present, present ? has : lacks];
    }),
  ];
  $("abilities").replaceChildren(
    ...items.map(([present, text]) => {
      const li = document.createElement("li");
      li.toggleAttribute("data-missing", !present);
      const mark = document.createElement("span");
      mark.className = "mark";
      mark.textContent = present ? "✓" : "–";
      li.append(mark, text);
      return li;
    }),
  );
}

async function refresh() {
  let info, songs;
  try {
    [info, songs] = await Promise.all([api("GET", "/api/info"), api("GET", "/api/songs")]);
  } catch {
    $("state").dataset.state = "offline";
    $("state").textContent = "Not answering";
    return;
  }
  const songsKey = JSON.stringify(songs.songs);
  if (shown.songs !== songsKey) {
    showSongs(songs.songs);
    shown.songs = songsKey;
  }
  if (shown.state === null) showBoard(info);
  shown.state = info;
  showState(info);
}

$("estop").addEventListener("click", () => command("/api/estop"));
$("stop").addEventListener("click", () => command("/api/stop"));
refresh();
setInterval(refresh, POLL_MS);
