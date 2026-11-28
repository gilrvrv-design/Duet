// The Duet web app, served by the device itself (docs/device-api.md). Plain JavaScript,
// no build step: what is here is what the board serves.
"use strict";

const POLL_MS = 1000;
const SERVER_CHECK_MS = 30000;  // how often the servers are checked again
const DEVICE_TIMEOUT_MS = 5000;  // the rig answers on its own network, quickly
const UPLOAD_TIMEOUT_MS = 60000;  // a long song or MIDI file over slow Wi-Fi
const SERVER_TIMEOUT_MS = 8000;  // a server that takes longer counts as not answering
const LIBRARY_SIZE = 20;  // duets shown from a server's library

// What each feature and channel means to a person; a board reports which it has.
const FEATURES = {
  wifi: ["Wi-Fi link to the Hub", "No Wi-Fi: the Hub connects over USB serial"],
  flash: ["Songs stay stored when the power is off", "Songs are kept in memory and lost at power-off"],
  play_button: ["A play button on the rig", "No play button: play songs from this page"],
  estop_button: ["A hardware emergency stop", "No hardware emergency stop: use the button on this page"],
  planner: [
    "MIDI files are planned on the rig, with no server",
    "No MIDI planner installed: load song files from the Hub, or use a server",
  ],
};
const CHANNELS = {
  carriage_striker: () => "A bot plays the bottles (carriage and striker)",
  led_strip: (c) => `Lights show the pianist's keys (${c.count} LEDs)`,
  midi_out: () => "A bot plays a digital piano over MIDI",
};
const STATES = { idle: "Ready", homing: "Getting ready…", playing: "Playing" };
const PRACTICE_STATES = {
  connecting: "Connecting to the rig…",
  playing: "Playing",
  done: "Done",
  stopped: "Stopped",
  failed: "Could not play",
};

// What the page knows, as last heard.
const state = {
  info: null,  // the rig's /api/info
  songsKey: null,  // the song list as last shown, to redraw it only when it changes
  titles: {},  // slot -> title of each stored song
  slots: 0,  // how many slots the rig has
  settings: null,  // the rig's settings
  serverChecks: [],  // [{url, state: "up" | "down" | "failing", detail}]
  libraryUrl: null,  // the server whose library is shown
  practice: null,  // {url, duet, view}: the practice chosen, as its server last said
};

// Talking to the rig and to servers -------------------------------------------------
// Every call goes through call(): a timeout, the answer checked, and a failure reported
// one way, as a Failure that says what went wrong in words for the person.

class Failure extends Error {
  constructor(message, answered) {
    super(message);
    this.answered = answered;  // false: nothing came back (off, unreachable, too slow)
  }
}

async function call(url, { method = "GET", body, type, timeoutMs }) {
  let reply;
  try {
    reply = await fetch(url, {
      method,
      body,
      headers: type ? { "Content-Type": type } : {},
      signal: AbortSignal.timeout(timeoutMs),
    });
  } catch {
    throw new Failure("did not answer", false);
  }
  const json = (reply.headers.get("Content-Type") || "").includes("json");
  const answer = json ? await reply.json() : await reply.text();
  if (!reply.ok) {
    // The rig says {"error": ..}; a server, a problem with its "detail".
    throw new Failure(answer.error || answer.detail || `error ${reply.status}`, true);
  }
  return answer;
}

function device(method, path, options = {}) {
  return call(path, { method, timeoutMs: DEVICE_TIMEOUT_MS, ...options });
}

function server(url, path, options = {}) {
  return call(`${url}${path}`, { timeoutMs: SERVER_TIMEOUT_MS, ...options });
}

function asJson(data) {
  return { body: JSON.stringify(data), type: "application/json" };
}

// Showing things --------------------------------------------------------------------

const $ = (id) => document.getElementById(id);

// An element with its properties and children: el("span", {className: "name"}, "Rain").
function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}

function button(text, label, onClick) {
  const b = el("button", { type: "button", className: "secondary", textContent: text });
  b.setAttribute("aria-label", label);
  b.addEventListener("click", onClick);
  return b;
}

function options(select, items) {  // items: [value, text]
  select.replaceChildren(...items.map(([value, text]) => el("option", { value, textContent: text })));
}

function say(text, kind = "error") {
  const message = $("message");
  message.textContent = text;
  message.dataset.kind = kind;
  message.setAttribute("role", kind === "error" ? "alert" : "status");
  message.hidden = !text;
}

function songLabel(slot) {
  return state.titles[slot] || `the song in slot ${slot}`;
}

// The rig --------------------------------------------------------------------------

// A command from a button; says why if the rig refuses it.
async function command(path) {
  try {
    await device("POST", path);
    say("");
  } catch (failure) {
    say(`The rig refused: ${failure.message}.`);
  }
  await refresh();
}

function showState(info) {
  const pill = $("state");
  const busy = info.state !== "idle";
  pill.dataset.state = info.estopped ? "estop" : info.state;
  pill.textContent = info.estopped
    ? "Emergency stop"
    : info.state === "playing"
      ? `Playing ${songLabel(info.slot)}`
      : STATES[info.state];
  $("stop").hidden = !busy;
  for (const li of $("songs").children) {
    li.toggleAttribute("data-playing", busy && Number(li.dataset.slot) === info.slot);
    li.querySelector("button").disabled = busy || info.estopped;
  }
}

function showSongs(songs) {
  state.titles = Object.fromEntries(songs.map((s) => [s.slot, s.title]));
  showSlots();
  $("songs").replaceChildren(
    ...songs.map(({ slot }) => {
      const play = button("Play", `Play ${songLabel(slot)}`, () =>
        command(`/api/songs/${slot}/play`),
      );
      const li = el("li", {}, el("span", { className: "name", textContent: songLabel(slot) }), play);
      li.dataset.slot = slot;
      return li;
    }),
  );
  $("no-songs").hidden = songs.length > 0;
}

function showBoard(info) {
  const { hello, channels } = info;
  offerMidi(hello.features.includes("planner"));
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
      const mark = el("span", { className: "mark", textContent: present ? "✓" : "–" });
      mark.setAttribute("aria-hidden", "true");
      const li = el("li", {}, mark, text);
      li.toggleAttribute("data-missing", !present);
      return li;
    }),
  );
}

async function refresh() {
  let info, songs;
  try {
    [info, songs] = await Promise.all([device("GET", "/api/info"), device("GET", "/api/songs")]);
  } catch {
    $("state").dataset.state = "offline";
    $("state").textContent = "Not answering";
    return;
  }
  state.slots = songs.slots;
  const songsKey = JSON.stringify(songs.songs);
  if (state.songsKey !== songsKey) {
    showSongs(songs.songs);
    state.songsKey = songsKey;
  }
  if (state.info === null) showBoard(info);
  if (state.info?.network !== info.network) placeSettings(info.network === "setup");
  state.info = info;
  showState(info);
}

// Songs: the slot to put one in, and loading one -----------------------------------

// The slots to put a song into; with none chosen, the first free one.
function showSlots() {
  const select = $("slot");
  const chosen = select.value;
  const all = Array.from({ length: state.slots }, (_, slot) => slot);
  options(
    select,
    all.map((slot) => [
      slot,
      state.titles[slot] ? `slot ${slot}: ${state.titles[slot]}` : `slot ${slot} (free)`,
    ]),
  );
  const free = all.find((slot) => !(slot in state.titles));
  select.value = chosen !== "" && Number(chosen) < state.slots ? chosen : String(free ?? 0);
}

// After a song is stored: the songs as the rig has them, and the next free slot chosen.
// (Re-chosen here every time: a store that leaves the song list unchanged, the same
// title into the same slot, would otherwise leave no slot chosen.)
async function afterStore() {
  await refresh();
  $("slot").value = "";
  showSlots();
}

// Stores a song file in the chosen slot.
async function storeSong(file, title) {
  const slot = Number($("slot").value);
  try {
    await device("PUT", `/api/songs/${slot}`, {
      body: file,
      type: "text/plain",
      timeoutMs: UPLOAD_TIMEOUT_MS,
    });
    say(`“${title}” is on the rig, in slot ${slot}.`, "ok");
  } catch (failure) {
    say(`The rig refused “${title}”: ${failure.message}.`);
  }
  await afterStore();
}

// The optional planner module (docs/design/esp-first.md): MIDI files only where it is.
function offerMidi(planner) {
  $("song-file").accept = planner ? ".song,.txt,.mid,.midi" : ".song,.txt";
  $("load-label").textContent = planner ? "Load a song or MIDI file" : "Load a song file";
  $("midi-hint").hidden = !planner;
}

// A MIDI file, planned by the rig itself; its title is the file's name.
async function loadMidiFile(file) {
  const title = file.name.replace(/\.midi?$/i, "");
  const slot = Number($("slot").value);
  try {
    const { warnings } = await device(
      "PUT",
      `/api/songs/${slot}/midi?title=${encodeURIComponent(title)}`,
      { body: file, type: "audio/midi", timeoutMs: UPLOAD_TIMEOUT_MS },
    );
    const notes = warnings.length ? ` (${warnings.join("; ")})` : "";
    say(`“${title}” is on the rig, in slot ${slot}${notes}.`, "ok");
  } catch (failure) {
    say(`The rig could not plan “${title}”: ${failure.message}.`);
  }
  await afterStore();
}

// A song file made by the Hub (duet song): its first line is its title.
async function loadFile(input) {
  const [file] = input.files;
  input.value = "";  // the same file can be chosen again
  if (/\.midi?$/i.test(file.name)) return loadMidiFile(file);
  const text = await file.text();
  let title = file.name;
  try {
    title = JSON.parse(text.slice(0, text.indexOf("\n"))).title || file.name;
  } catch {
    // not a song file: the rig says why when it refuses it
  }
  await storeSong(text, title);
}

// Settings ------------------------------------------------------------------------

async function loadSettings() {
  state.settings = await device("GET", "/api/settings");
  $("wifi-ssid").value = state.settings.wifi_ssid;
  $("wifi-password").value = "";
  $("servers").value = state.settings.servers.join("\n");
  showPasswordHint();
}

function showPasswordHint() {
  const { wifi_password_set, wifi_ssid } = state.settings;
  $("password-hint").textContent =
    wifi_password_set && $("wifi-ssid").value === wifi_ssid
      ? "Leave empty to keep the saved password."
      : "Leave empty for an open network.";
}

// On the setup network the form comes first; once on Wi-Fi it is at the end.
function placeSettings(setup) {
  $("settings-title").textContent = setup ? "Connect to Wi-Fi" : "Settings";
  $("setup-intro").hidden = !setup;
  if (setup) $("estop").after($("settings"));
  else document.querySelector("main").append($("settings"));
}

async function saveSettings(event) {
  event.preventDefault();
  const ssid = $("wifi-ssid").value;
  const password = $("wifi-password").value;
  const wanted = {
    wifi_ssid: ssid,
    servers: $("servers").value.split("\n").map((s) => s.trim()).filter(Boolean),
  };
  const keeps = password === "" && state.settings.wifi_password_set && ssid === state.settings.wifi_ssid;
  if (!keeps) wanted.wifi_password = password;
  let answer;
  try {
    answer = await device("POST", "/api/settings", asJson(wanted));
  } catch (failure) {
    say(`Not saved: ${failure.message}.`);
    return;
  }
  say(
    answer.restart
      ? `Saved. The rig is restarting to join “${ssid}”. Connect this device to “${ssid}” ` +
          `too, then open http://${state.info.hello.device_id}.local`
      : "Saved.",
    "ok",
  );
  try {
    await loadSettings();
    await checkServers();
  } catch (failure) {
    // Restarting to join a network, the rig may not answer for a while; refresh shows
    // "Not answering" until it does. Any other failure is the person's to see.
    if (!answer.restart) say(`Saved, but the rig did not answer after: ${failure.message}.`);
  }
}

// Servers and the library ----------------------------------------------------------
// Servers add the library and practice when they can be reached; without one the rig
// still plays what is stored on it (docs/design/esp-first.md).

async function checkServer(url) {
  try {
    const health = await server(url, "/v1/health");
    return health.status === "ok"
      ? { url, state: "up", detail: `up, version ${health.version}` }
      : { url, state: "failing", detail: "not ready" };
  } catch (failure) {
    return failure.answered
      ? { url, state: "failing", detail: failure.message }
      : { url, state: "down", detail: "not reachable" };
  }
}

async function checkServers() {
  const urls = state.settings.servers.map((u) => u.replace(/\/+$/, ""));
  state.serverChecks = await Promise.all(urls.map(checkServer));
  $("server-list").replaceChildren(
    ...state.serverChecks.map(({ url, state: up, detail }) => {
      const dot = el("span", { className: "dot" });
      dot.setAttribute("aria-hidden", "true");
      const li = el(
        "li",
        {},
        dot,
        el("span", { className: "url", textContent: url }),
        el("span", { className: "detail", textContent: detail }),
      );
      li.dataset.state = up;
      return li;
    }),
  );
  const up = state.serverChecks.find((s) => s.state === "up");
  if (up?.url !== state.libraryUrl) await showLibrary(up?.url ?? null);
}

async function showLibrary(url) {
  state.libraryUrl = url;
  $("duets").replaceChildren();
  if (url === null) {
    $("library-note").textContent = state.settings.servers.length
      ? "No server can be reached. The rig still plays the songs stored on it."
      : "Add a server in Settings for the library. Without one, the rig plays the songs stored on it.";
    return;
  }
  let duets;
  try {
    duets = await server(url, `/v1/duets?limit=${LIBRARY_SIZE}`);
  } catch (failure) {
    $("library-note").textContent = `The library on ${url} did not answer (${failure.message}).`;
    return;
  }
  $("library-note").textContent = duets.length ? `From ${url}` : `The library on ${url} is empty.`;
  $("duets").replaceChildren(...duets.map((duet) => duetRow(url, duet)));
}

function duetRow(url, duet) {
  const name = el(
    "span",
    { className: "name", textContent: duet.title },
    el("span", { className: "meta", textContent: `${duet.bars} bars · level ${duet.difficulty}` }),
  );
  const buttons = el(
    "div",
    { className: "buttons" },
    button("Practise", `Practise ${duet.title}`, () => choosePractice(url, duet)),
    button("Put on the rig", `Put ${duet.title} on the rig`, () => putOnRig(url, duet)),
  );
  return el("li", {}, name, buttons);
}

// The server makes a song file of the duet for this rig; the rig stores it.
async function putOnRig(url, duet) {
  const { hello, channels } = state.info;
  const rig = {
    profile: hello.profile,
    channels: Object.fromEntries(channels.map((c) => [c.kind, c.ch])),
  };
  let file;
  try {
    file = await server(url, `/v1/duets/${duet.id}/song`, { method: "POST", ...asJson(rig) });
  } catch (failure) {
    if (!failure.answered) {
      say(`${url} stopped answering.`);
      await checkServers();
    } else {
      say(`The server could not make a song of “${duet.title}”: ${failure.message}`);
    }
    return;
  }
  await storeSong(file, duet.title);
}

// Practice ------------------------------------------------------------------------
// The server plays the duet on this rig, live, while it listens to the pianist through
// an input on its own machine (docs/device-api.md, "Practice").

function practising() {
  return state.practice?.view && !over(state.practice.view);
}

function over(view) {
  return ["done", "stopped", "failed"].includes(view.state);
}

async function choosePractice(url, duet) {
  if (practising()) {
    say("A practice is playing: stop it first.");
    return;
  }
  let inputs;
  try {
    ({ inputs } = await server(url, "/v1/live/inputs"));
  } catch (failure) {
    say(`The server cannot practise now: ${failure.message}.`);
    return;
  }
  state.practice = { url, duet, view: null };
  $("practice").hidden = false;
  $("practice-title").textContent = duet.title;
  $("practice-status").textContent = "";
  $("practice-result").hidden = true;
  options($("practice-input"), inputs.map((name) => [name, name]));
  const listens = inputs.length > 0;
  $("practice-input").disabled = !listens;
  for (const mode of ["wait", "follow"])
    $("practice-mode").querySelector(`[value=${mode}]`).disabled = !listens;
  if (!listens) $("practice-mode").value = "play";
  $("practice-note").hidden = listens;
  $("practice").scrollIntoView({ block: "nearest" });
}

function showPractice(view) {
  state.practice.view = view;
  const mode = $("practice-mode").querySelector(`[value=${view.mode}]`).textContent;
  $("practice-status").textContent =
    view.state === "playing" ? `${PRACTICE_STATES.playing}: ${mode}` : PRACTICE_STATES[view.state];
  $("practice-result").textContent = view.detail;
  $("practice-result").hidden = !view.detail;
  $("practice-start").hidden = !over(view);
  $("practice-stop").hidden = over(view);
}

async function startPractice() {
  const { url, duet } = state.practice;
  const mode = $("practice-mode").value;
  const wanted = {
    duet_id: duet.id,
    rig: state.info.link,
    profile: state.info.hello.profile,
    mode,
    input: mode === "play" ? null : $("practice-input").value,
  };
  try {
    showPractice(await server(url, "/v1/live", { method: "POST", ...asJson(wanted) }));
  } catch (failure) {
    say(`The server could not start it: ${failure.message}`);
    return;
  }
  say("");
  setTimeout(followPractice, POLL_MS);
}

async function stopPractice() {
  const { url, view } = state.practice;
  try {
    showPractice(await server(url, `/v1/live/${view.id}/stop`, { method: "POST" }));
  } catch (failure) {
    say(`The server could not stop it: ${failure.message}.`);
  }
}

// While a practice plays, the page follows it, on its own poll.
async function followPractice() {
  if (!practising()) return;
  const { url, view } = state.practice;
  try {
    showPractice(await server(url, `/v1/live/${view.id}`));
  } catch (failure) {
    $("practice-status").textContent = failure.answered
      ? `The practice is gone: ${failure.message}.`
      : `${url} stopped answering.`;
    if (failure.answered) return;  // nothing more to follow
  }
  setTimeout(followPractice, POLL_MS);
}

// The page ------------------------------------------------------------------------

// Runs ``task`` now and again ``ms`` after each run ends, so runs never pile up.
async function every(ms, task) {
  await task();
  setTimeout(() => every(ms, task), ms);
}

$("estop").addEventListener("click", () => command("/api/estop"));
$("stop").addEventListener("click", () => command("/api/stop"));
$("settings-form").addEventListener("submit", saveSettings);
$("practice-start").addEventListener("click", startPractice);
$("practice-stop").addEventListener("click", stopPractice);
$("song-file").addEventListener("change", (event) => loadFile(event.target));
$("wifi-ssid").addEventListener("input", showPasswordHint);
every(POLL_MS, refresh);
loadSettings().then(() => every(SERVER_CHECK_MS, checkServers));
