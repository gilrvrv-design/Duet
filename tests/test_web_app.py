"""The web app the device serves (firmware/web/), in a real browser against the native
device. Set DUET_CHROMIUM to a Chromium binary to use it instead of Playwright's own."""

import os

import pytest
from playwright.sync_api import Page, expect, sync_playwright

import native_device
from duet.device.gateway import DeviceGateway
from duet.profile import keyboard_profile, robot_profile
from duet.score import load_score
from duet.sim import RIG_CHANNELS
from duet.songs import compile_song
from helpers import ROOT


@pytest.fixture
def device():
    running = native_device.start()
    try:
        yield running
    finally:
        running.stop()


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        launched = p.chromium.launch(executable_path=os.environ.get("DUET_CHROMIUM"))
        yield launched
        launched.close()


@pytest.fixture
def page(browser, device):
    """The app, with its clock under the test's control: it polls only when told."""
    opened = browser.new_page(viewport={"width": 390, "height": 760})
    opened.clock.install()
    yield opened
    opened.close()


def upload(device, slot):
    score = load_score(ROOT / "examples" / "rain-on-the-bottles.json")
    song = compile_song(score, robot_profile(), keyboard_profile(), RIG_CHANNELS)
    gateway = DeviceGateway(device.serial_url, profile=robot_profile()).connect()
    try:
        gateway.upload(slot, song.commands)
    finally:
        gateway.close()


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
    expect(page.locator("#no-songs")).to_be_visible()


def test_play_a_stored_song_and_stop_it(page, device):
    page.goto(device.http_url)
    upload(device, 3)
    poll(page)  # the app sees the new song
    expect(page.locator("#no-songs")).to_be_hidden()
    page.get_by_role("button", name="Play slot 3").click()
    expect(page.locator("#state")).to_have_text("Homing for slot 3")
    expect(page.get_by_role("button", name="Play slot 3")).to_be_disabled()
    assert device.api("GET", "/api/info")[1]["state"] != "idle"

    page.get_by_role("button", name="Stop", exact=True).click()
    expect(page.locator("#state")).to_have_text("Ready")
    expect(page.get_by_role("button", name="Stop", exact=True)).to_be_hidden()
    assert device.api("GET", "/api/info")[1]["state"] == "idle"


def test_emergency_stop_and_a_refusal(page, device):
    upload(device, 1)
    page.goto(device.http_url)
    device.api("POST", "/api/estop")  # someone else stops the rig; the page has not polled
    page.get_by_role("button", name="Play slot 1").click()
    expect(page.locator("#message")).to_have_text("The rig refused: emergency stop.")
    expect(page.locator("#state")).to_have_text("Emergency stop")
    expect(page.get_by_role("button", name="Play slot 1")).to_be_disabled()


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
