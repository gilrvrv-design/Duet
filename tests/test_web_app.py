"""The web app the device serves (firmware/web/), in a real browser against the native
device. Set DUET_CHROMIUM to a Chromium binary to use it instead of Playwright's own."""

from playwright.sync_api import Page, expect

from duet.cli import main
from helpers import ROOT


def poll(page: Page) -> None:
    page.clock.run_for(1000)  # one poll of the device


def test_the_page_shows_what_the_board_can_do(page, device):
    page.goto(device.http_url)
    expect(page.locator("#device")).to_have_text("duet-rig-1 · native")
    expect(page.locator("#state")).to_have_text("Ready")
    abilities = page.locator("#abilities li")
    expect(abilities.filter(has_text="A bot plays the bottles")).to_have_count(1)
    expect(abilities.filter(has_text="176 LEDs")).to_have_count(1)
    expect(abilities.filter(has_text="A bot plays a digital piano over MIDI")).to_have_count(1)
    missing = page.locator("#abilities li[data-missing]")
    expect(missing.filter(has_text="lost at power-off")).to_have_count(1)  # no flash
    expect(missing.filter(has_text="No hardware emergency stop")).to_have_count(1)
    expect(missing.filter(has_text="No MIDI planner installed")).to_have_count(1)
    expect(page.locator("#song-file")).to_have_attribute("accept", ".song,.txt")  # no MIDI
    expect(page.locator("#no-songs")).to_be_visible()


def test_play_a_stored_song_and_stop_it(page, device):
    page.goto(device.http_url)
    device.store_example(3)
    poll(page)  # the app sees the new song
    expect(page.locator("#no-songs")).to_be_hidden()
    page.get_by_role("button", name="Play Rain on the Bottles").click()
    expect(page.locator("#state")).to_have_text("Getting ready…")
    expect(page.get_by_role("button", name="Play Rain on the Bottles")).to_be_disabled()
    assert device.api("GET", "/api/info")[1]["state"] != "idle"

    page.get_by_role("button", name="Stop", exact=True).click()
    expect(page.locator("#state")).to_have_text("Ready")
    expect(page.get_by_role("button", name="Stop", exact=True)).to_be_hidden()
    assert device.api("GET", "/api/info")[1]["state"] == "idle"


def test_emergency_stop_and_a_refusal(page, device):
    device.store_example(1)
    page.goto(device.http_url)
    device.api("POST", "/api/estop")  # someone else stops the rig; the page has not polled
    page.get_by_role("button", name="Play Rain on the Bottles").click()
    expect(page.locator("#message")).to_have_text("The rig refused: emergency stop.")
    expect(page.locator("#state")).to_have_text("Emergency stop")
    expect(page.get_by_role("button", name="Play Rain on the Bottles")).to_be_disabled()


def test_the_estop_button_stops_the_rig(page, device):
    page.goto(device.http_url)
    page.get_by_role("button", name="Emergency stop").click()
    expect(page.locator("#state")).to_have_text("Emergency stop")
    assert device.api("GET", "/api/info")[1]["estopped"] is True


def test_the_page_says_when_the_device_stops_answering(page, device):
    page.goto(device.http_url)
    expect(page.locator("#state")).to_have_text("Ready")
    device.stop()
    poll(page)
    expect(page.locator("#state")).to_have_text("Not answering")


def test_a_new_board_asks_for_wifi_first(page, device):
    page.goto(device.http_url)
    expect(page.get_by_role("heading", name="Connect to Wi-Fi")).to_be_visible()
    page.get_by_label("Wi-Fi network").fill("Home")
    page.get_by_label("Wi-Fi password").fill("correct horse")
    page.get_by_label("Servers").fill("https://duet.example\n\n http://10.0.0.2:8000 ")
    page.get_by_role("button", name="Save").click()
    expect(page.locator("#message")).to_contain_text("restarting to join “Home”")
    assert device.api("GET", "/api/settings")[1] == {
        "wifi_ssid": "Home",
        "wifi_password_set": True,
        "servers": ["https://duet.example", "http://10.0.0.2:8000"],
    }
    poll(page)  # the board has joined: the form moves to the end
    expect(page.get_by_role("heading", name="Settings")).to_be_visible()
    expect(page.locator("#password-hint")).to_have_text("Leave empty to keep the saved password.")


def test_changing_servers_keeps_the_password(page, device):
    home = {"wifi_ssid": "Home", "wifi_password": "correct horse", "servers": []}
    device.api("POST", "/api/settings", home)
    page.goto(device.http_url)
    expect(page.get_by_label("Wi-Fi network")).to_have_value("Home")
    page.get_by_label("Servers").fill("https://duet.example")
    page.get_by_role("button", name="Save").click()
    expect(page.locator("#message")).to_have_text("Saved.")
    status, settings = device.api("GET", "/api/settings")
    assert settings["wifi_password_set"] and settings["servers"] == ["https://duet.example"]


def test_a_refused_setting_says_why(page, device):
    page.goto(device.http_url)
    page.get_by_label("Wi-Fi network").fill("Home")
    page.get_by_label("Wi-Fi password").fill("short")
    page.get_by_role("button", name="Save").click()
    expect(page.locator("#message")).to_contain_text("Not saved: a Wi-Fi password is 8-63")
    assert device.api("GET", "/api/settings")[1]["wifi_ssid"] == ""


def test_a_song_file_from_the_hub_goes_onto_the_rig(page, device, tmp_path):
    """No server and no planner needed: the Hub made the file (duet song)."""
    song = tmp_path / "rain.song"
    assert main(["song", str(ROOT / "examples" / "rain-on-the-bottles.json"), "-o", str(song)]) == 0
    page.goto(device.http_url)
    expect(page.locator("#slot")).to_have_value("0")
    page.get_by_label("Load a song file").set_input_files(song)
    expect(page.locator("#message")).to_have_text("“Rain on the Bottles” is on the rig, in slot 0.")
    assert device.api("GET", "/api/songs")[1]["songs"] == [
        {"slot": 0, "title": "Rain on the Bottles"}
    ]
    page.get_by_role("button", name="Play Rain on the Bottles").click()
    expect(page.locator("#state")).not_to_have_text("Ready")


def test_a_broken_song_file_is_refused(page, device, tmp_path):
    broken = tmp_path / "broken.song"
    broken.write_text('{"title":"Broken"}\n{"type":"strike_at","seq":0,"ch":0,"t_us":-1}\n')
    page.goto(device.http_url)
    page.get_by_label("Load a song file").set_input_files(broken)
    expect(page.locator("#message")).to_have_text("The rig refused “Broken”: bad song line 2.")
    assert device.api("GET", "/api/songs")[1]["songs"] == []
