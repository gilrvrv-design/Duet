"""The web app with servers up, down and failing (docs/design/esp-first.md, step 4): it
uses a server's library when one answers, and falls back to the songs on the rig."""

import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import uvicorn
from playwright.sync_api import expect

from duet.api.app import create_app
from duet.listening import SimulatedPianist
from duet.storage import MemoryStore
from helpers import ROOT


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LibraryServer:
    """The real server app, with the example duets in its library."""

    def __init__(self, live_inputs=None) -> None:
        app = create_app(
            store=MemoryStore(), examples_dir=ROOT / "examples", live_inputs=live_inputs or {}
        )
        self.url = f"http://127.0.0.1:{free_port()}"
        port = int(self.url.rsplit(":", 1)[1])
        self._server = uvicorn.Server(uvicorn.Config(app, port=port, log_level="warning"))
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self._server.started:
            assert time.monotonic() < deadline, "the server did not start"
            time.sleep(0.02)

    def stop(self) -> None:
        self._server.should_exit = True
        self._thread.join(timeout=10)


@pytest.fixture
def library():
    server = LibraryServer()
    yield server.url
    server.stop()


class Failing(BaseHTTPRequestHandler):
    """A server that is up but broken: every request is a 503 (with CORS, so the page
    sees the error rather than a blocked request)."""

    def do_GET(self) -> None:
        self.send_response(503)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def failing():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Failing)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


@pytest.fixture
def down():
    return f"http://127.0.0.1:{free_port()}"  # nothing listens there


def use_servers(device, *urls) -> None:
    settings = {"wifi_ssid": "Home", "wifi_password": "correct horse", "servers": list(urls)}
    assert device.api("POST", "/api/settings", settings)[0] == 200


def test_without_servers_the_rig_plays_what_it_has(page, device):
    device.store_example(2)
    page.goto(device.http_url)
    expect(page.locator("#library-note")).to_have_text(
        "Add a server in Settings for the library. Without one, the rig plays the songs "
        "stored on it."
    )
    page.get_by_role("button", name="Play Rain on the Bottles").click()
    expect(page.locator("#state")).not_to_have_text("Ready")


def test_a_library_song_goes_onto_the_rig(page, device, library):
    use_servers(device, library)
    page.goto(device.http_url)
    expect(page.locator("#server-list li[data-state=up]")).to_contain_text(library)
    expect(page.locator("#library-note")).to_have_text(f"From {library}")
    expect(page.locator("#slot")).to_have_value("0")  # the first free slot
    page.get_by_role("button", name="Put Rain on the Bottles on the rig").click()
    expect(page.locator("#message")).to_have_text("“Rain on the Bottles” is on the rig, in slot 0.")
    assert device.api("GET", "/api/songs")[1]["songs"] == [
        {"slot": 0, "title": "Rain on the Bottles"}
    ]
    expect(page.locator("#slot")).to_have_value("1")  # the next one goes into the next slot
    page.get_by_role("button", name="Play Rain on the Bottles").click()  # no server needed
    expect(page.locator("#state")).not_to_have_text("Ready")


def test_servers_up_down_and_failing(page, device, library, down, failing):
    use_servers(device, down, failing, library)
    page.goto(device.http_url)
    servers = page.locator("#server-list li")
    expect(servers).to_have_count(3)
    expect(servers.nth(0)).to_have_attribute("data-state", "down")
    expect(servers.nth(0)).to_contain_text("not reachable")
    expect(servers.nth(1)).to_have_attribute("data-state", "failing")
    expect(servers.nth(1)).to_contain_text("error 503")
    expect(servers.nth(2)).to_have_attribute("data-state", "up")
    expect(page.locator("#library-note")).to_have_text(f"From {library}")  # the one that works


def test_when_no_server_answers_the_rig_still_plays(page, device, down, failing):
    use_servers(device, down, failing)
    device.store_example(5)
    page.goto(device.http_url)
    expect(page.locator("#library-note")).to_have_text(
        "No server can be reached. The rig still plays the songs stored on it."
    )
    expect(page.locator("#duets li")).to_have_count(0)
    page.get_by_role("button", name="Play Rain on the Bottles").click()
    expect(page.locator("#state")).not_to_have_text("Ready")


def test_a_server_that_goes_away(page, device):
    server = LibraryServer()
    use_servers(device, server.url)
    page.goto(device.http_url)
    expect(page.locator("#library-note")).to_have_text(f"From {server.url}")
    server.stop()
    page.get_by_role("button", name="Put Rain on the Bottles on the rig").click()
    expect(page.locator("#message")).to_have_text(f"{server.url} stopped answering.")
    expect(page.locator("#server-list li")).to_have_attribute("data-state", "down")
    expect(page.locator("#library-note")).to_have_text(
        "No server can be reached. The rig still plays the songs stored on it."
    )
    assert device.api("GET", "/api/songs")[1]["songs"] == []


# Practice: the server plays a duet on the rig, live, listening to the pianist ----------

PIANIST = "Simulated pianist"


@pytest.fixture
def listening():
    """A library server that hears the pianist (here a simulated one)."""
    server = LibraryServer({PIANIST: lambda _robot: SimulatedPianist(reaction_s=0.2)})
    yield server.url
    server.stop()


def poll_until(page, locator, text, timeout_s=60):
    deadline = time.monotonic() + timeout_s
    while text not in (locator.text_content() or ""):
        assert time.monotonic() < deadline, f"no {text!r}: {locator.text_content()!r}"
        page.clock.run_for(1000)  # the page follows the practice with each refresh
        time.sleep(0.2)


def test_practise_with_the_rig_waiting_for_me(page, device, listening):
    use_servers(device, listening)
    page.goto(device.http_url)
    page.get_by_role("button", name="Practise Rain on the Bottles").click()
    expect(page.locator("#practice-title")).to_have_text("Rain on the Bottles")
    expect(page.locator("#practice-input")).to_have_value(PIANIST)
    page.locator("#practice-mode").select_option("wait")
    page.get_by_role("button", name="Start").click()
    poll_until(page, page.locator("#practice-status"), "Done")
    result = page.locator("#practice-result").text_content()
    assert result.startswith("waited ") and "notes" in result  # how long, and the grade
    expect(page.get_by_role("button", name="Start")).to_be_visible()  # ready to go again


def test_stop_a_practice(page, device, listening):
    use_servers(device, listening)
    page.goto(device.http_url)
    page.get_by_role("button", name="Practise Rain on the Bottles").click()
    page.get_by_role("button", name="Start").click()  # play together
    poll_until(page, page.locator("#practice-status"), "Playing: Play together")
    page.get_by_role("button", name="Stop", exact=True).last.click()
    poll_until(page, page.locator("#practice-status"), "Stopped")


def test_a_server_that_cannot_listen_only_plays_together(page, device, library):
    use_servers(device, library)
    page.goto(device.http_url)
    page.get_by_role("button", name="Practise Rain on the Bottles").click()
    expect(page.locator("#practice-note")).to_contain_text("can only play together")
    expect(page.locator("#practice-mode option[value=wait]")).to_be_disabled()
    expect(page.locator("#practice-mode")).to_have_value("play")
