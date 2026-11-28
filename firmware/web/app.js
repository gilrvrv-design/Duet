// The Duet web app, served by the device itself (docs/device-api.md). Plain JavaScript,
// no build step: what is here is what the board serves.
"use strict";

const POLL_MS = 1000;
const SERVER_CHECK_MS = 30000;  // how often the servers are checked again
const SERVER_TIMEOUT_MS = 4000;  // a server that takes longer counts as not reachable

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

function say(text, kind = "error") {
  $("message").textContent = text;
  $("message").dataset.kind = kind;
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
      homing: "Getting ready…",
      playing: `Playing ${songTitle(info.slot)}`,
    }[info.state];
  }
  $("stop").hidden = !playing;
  for (const li of $("songs").children) {
    const here = playing && Number(li.dataset.slot) === info.slot;
    li.toggleAttribute("data-playing", here);
    li.querySelector("button").disabled = playing || info.estopped;
  }
}

let titles = {};  // slot -> title, of the songs shown
let slots = 0;  // how many the rig has

function songTitle(slot) {
  return titles[slot] || `slot ${slot}`;
}

function showSongs(songs) {
  titles = Object.fromEntries(songs.map((s) => [s.slot, s.title]));
  showSlots();
  const list = $("songs");
  list.replaceChildren(
    ...songs.map(({ slot, title }) => {
      const li = document.createElement("li");
      li.dataset.slot = slot;
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = title || `Song in slot ${slot}`;
      const play = document.createElement("button");
      play.type = "button";
      play.className = "secondary";
      play.textContent = "Play";
      play.setAttribute("aria-label", `Play ${title || `slot ${slot}`}`);
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

// Settings ----------------------------------------------------------------------

let saved = null;  // the settings as the device has them

async function loadSettings() {
  saved = await api("GET", "/api/settings");
  $("wifi-ssid").value = saved.wifi_ssid;
  $("wifi-password").value = "";
  $("servers").value = saved.servers.join("\n");
  showPasswordHint();
}

function showPasswordHint() {
  const keeps = saved.wifi_password_set && $("wifi-ssid").value === saved.wifi_ssid;
  $("password-hint").textContent = keeps
    ? "Leave empty to keep the saved password."
    : "Leave empty for an open network.";
}

// On the setup network the form comes first; once on Wi-Fi it is at the end.
function placeSettings(setup) {
  const section = $("settings");
  $("settings-title").textContent = setup ? "Connect to Wi-Fi" : "Settings";
  $("setup-intro").hidden = !setup;
  if (setup) $("estop").after(section);
  else document.querySelector("main").append(section);
}

async function saveSettings(event) {
  event.preventDefault();
  const ssid = $("wifi-ssid").value;
  const password = $("wifi-password").value;
  const body = {
    wifi_ssid: ssid,
    servers: $("servers").value.split("\n").map((s) => s.trim()).filter(Boolean),
  };
  const keeps = password === "" && saved.wifi_password_set && ssid === saved.wifi_ssid;
  if (!keeps) body.wifi_password = password;
  const reply = await fetch("/api/settings", { method: "POST", body: JSON.stringify(body) });
  const answer = await reply.json();
  if (!reply.ok) {
    say(`Not saved: ${answer.error}.`);
    return;
  }
  if (answer.restart) {
    say(
      `Saved. The rig is restarting to join “${ssid}”. Connect this device to “${ssid}” ` +
        `too, then open http://${shown.state.hello.device_id}.local`,
      "ok",
    );
  } else {
    say("Saved.", "ok");
  }
  await loadSettings();
  await checkServers();
}

// Servers and the library ----------------------------------------------------------
// Servers add the library (and, later, composing and lessons) when they can be reached;
// without one the rig still plays what is stored on it (docs/design/esp-first.md).

let servers = [];  // [{url, state: "up" | "down" | "failing", detail}], as last checked
let library = null;  // the server whose library is shown

async function checkServer(url) {
  try {
    const reply = await fetch(`${url}/v1/health`, {
      signal: AbortSignal.timeout(SERVER_TIMEOUT_MS),
    });
    if (!reply.ok) return { url, state: "failing", detail: `error ${reply.status}` };
    const health = await reply.json();
    return health.status === "ok"
      ? { url, state: "up", detail: `version ${health.version}` }
      : { url, state: "failing", detail: "not ready" };
  } catch {
    return { url, state: "down", detail: "not reachable" };
  }
}

async function checkServers() {
  const urls = saved.servers.map((u) => u.replace(/\/+$/, ""));
  servers = await Promise.all(urls.map(checkServer));
  showServers();
  const up = servers.find((s) => s.state === "up");
  if (up?.url !== library) await showLibrary(up?.url ?? null);
}

function showServers() {
  $("server-list").replaceChildren(
    ...servers.map(({ url, state, detail }) => {
      const li = document.createElement("li");
      li.dataset.state = state;
      const dot = document.createElement("span");
      dot.className = "dot";
      const name = document.createElement("span");
      name.className = "url";
      name.textContent = url;
      const what = document.createElement("span");
      what.className = "detail";
      what.textContent = detail;
      li.append(dot, name, what);
      return li;
    }),
  );
}

async function showLibrary(url) {
  library = url;
  $("duets").replaceChildren();
  $("library-slot").hidden = true;
  if (url === null) {
    $("library-note").textContent = saved.servers.length
      ? "No server can be reached. The rig still plays the songs stored on it."
      : "Add a server in Settings for the library. Without one, the rig plays the songs stored on it.";
    return;
  }
  let duets;
  try {
    const reply = await fetch(`${url}/v1/duets?limit=20`, {
      signal: AbortSignal.timeout(SERVER_TIMEOUT_MS),
    });
    if (!reply.ok) throw new Error(`error ${reply.status}`);
    duets = await reply.json();
  } catch (failed) {
    $("library-note").textContent = `The library on ${url} did not answer (${failed.message}).`;
    return;
  }
  $("library-note").textContent = duets.length
    ? `From ${url}`
    : `The library on ${url} is empty.`;
  $("library-slot").hidden = duets.length === 0;
  $("duets").replaceChildren(...duets.map((duet) => duetRow(url, duet)));
}

function duetRow(url, duet) {
  const li = document.createElement("li");
  const name = document.createElement("span");
  name.className = "name";
  name.textContent = duet.title;
  const meta = document.createElement("span");
  meta.className = "meta";
  meta.textContent = `${duet.bars} bars · level ${duet.difficulty}`;
  name.append(meta);
  const put = document.createElement("button");
  put.type = "button";
  put.className = "secondary";
  put.textContent = "Put on the rig";
  put.setAttribute("aria-label", `Put ${duet.title} on the rig`);
  put.addEventListener("click", () => putOnRig(url, duet, Number($("slot").value)));
  li.append(name, put);
  return li;
}

// The slots to put a song into: the first free one is chosen.
function showSlots() {
  const select = $("slot");
  const chosen = select.value;
  select.replaceChildren(
    ...Array.from({ length: slots }, (_, slot) => {
      const option = document.createElement("option");
      option.value = slot;
      option.textContent = titles[slot] ? `slot ${slot}: ${titles[slot]}` : `slot ${slot} (free)`;
      return option;
    }),
  );
  const free = Array.from({ length: slots }, (_, s) => s).find((s) => !(s in titles));
  select.value = chosen !== "" && chosen < slots ? chosen : String(free ?? 0);
}

// The server makes a song file of the duet for this rig; the rig stores it.
async function putOnRig(url, duet, slot) {
  const { hello, channels } = shown.state;
  const rig = {
    profile: hello.profile,
    channels: Object.fromEntries(channels.map((c) => [c.kind, c.ch])),
  };
  let file;
  try {
    const reply = await fetch(`${url}/v1/duets/${duet.id}/song`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(rig),
    });
    if (!reply.ok) {
      const problem = await reply.json();
      say(`The server could not make a song of “${duet.title}”: ${problem.detail}`);
      return;
    }
    file = await reply.text();
  } catch {
    say(`${url} stopped answering.`);
    await checkServers();
    return;
  }
  const stored = await fetch(`/api/songs/${slot}`, {
    method: "PUT",
    headers: { "Content-Type": "text/plain" },
    body: file,
  });
  if (stored.ok) {
    say(`“${duet.title}” is on the rig, in slot ${slot}.`, "ok");
    $("slot").value = "";  // the next song goes into the next free slot
  }
  else {
    say(`The rig refused: ${(await stored.json()).error}.`);
  }
  await refresh();
}

// The page ------------------------------------------------------------------------

async function refresh() {
  let info, songs;
  try {
    [info, songs] = await Promise.all([api("GET", "/api/info"), api("GET", "/api/songs")]);
    slots = songs.slots;
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
  if (shown.state?.network !== info.network) placeSettings(info.network === "setup");
  shown.state = info;
  showState(info);
}

$("estop").addEventListener("click", () => command("/api/estop"));
$("stop").addEventListener("click", () => command("/api/stop"));
$("settings-form").addEventListener("submit", saveSettings);
$("wifi-ssid").addEventListener("input", showPasswordHint);
refresh();
setInterval(refresh, POLL_MS);
loadSettings().then(checkServers);
setInterval(checkServers, SERVER_CHECK_MS);
