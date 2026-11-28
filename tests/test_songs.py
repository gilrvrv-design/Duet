def test_a_title_fits_the_device():
    from duet.protocol import TITLE_BYTES
    from duet.songs import song_title

    assert song_title("Rain  on\nthe Bottles") == "Rain on the Bottles"  # one line
    long = song_title("Über " * 30)
    assert len(long.encode()) <= TITLE_BYTES and long.endswith("…")
    assert long.startswith("Über Über")
