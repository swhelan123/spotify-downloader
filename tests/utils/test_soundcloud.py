import pytest

from spotdl.types.song import Song
from spotdl.utils.search import reinit_song
from spotdl.utils.soundcloud import (
    clean_name,
    is_soundcloud_song,
    is_soundcloud_url,
    normalize_url,
    split_title,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        (
            "https://soundcloud.com/fredagain/delilah-pull-me-out-of-this?si=abc&utm_source=x",
            "https://soundcloud.com/fredagain/delilah-pull-me-out-of-this",
        ),
        (
            "https://m.soundcloud.com/fredagain/sets/actual-life-3-january-1/",
            "https://soundcloud.com/fredagain/sets/actual-life-3-january-1",
        ),
        (
            "www.soundcloud.com/fredagain",
            "https://soundcloud.com/fredagain",
        ),
    ],
)
def test_normalize_url(url, expected):
    assert normalize_url(url) == expected


@pytest.mark.parametrize(
    "title, username, name, artists",
    [
        (
            "Delilah (pull me out of this)",
            "Fred again..",
            "Delilah (pull me out of this)",
            ["Fred again.."],
        ),
        (
            "Fred Again - Delilah (ATYYA Flip)",
            "ATYYA",
            "Delilah (ATYYA Flip)",
            ["Fred Again"],
        ),
        (
            "Artist A, Artist B - Song [FREE DL]",
            "label",
            "Song",
            ["Artist A", "Artist B"],
        ),
        (
            "Artist A x Artist B - Song (feat. Artist C)",
            "label",
            "Song",
            ["Artist A", "Artist B", "Artist C"],
        ),
        ("Song ft. Artist C", "Artist A", "Song", ["Artist A", "Artist C"]),
    ],
)
def test_split_title(title, username, name, artists):
    result = split_title(title, username)

    assert result["name"] == name
    assert result["artists"] == artists


def test_clean_name():
    assert (
        clean_name("Delilah (Pull Me Out Of This) [Out Now]")
        == "delilah pull me out of this"
    )
    assert clean_name("Song - X Remix") == clean_name("Song (X Remix)")


def test_soundcloud_song_is_not_reinitialized():
    song = Song.from_missing_data(
        name="Song",
        artists=["Artist"],
        artist="Artist",
        url="https://soundcloud.com/artist/song",
        download_url="https://soundcloud.com/artist/song",
    )

    assert is_soundcloud_url(song.url)
    assert is_soundcloud_song(song)
    assert reinit_song(song) is song


def test_spotify_song_is_not_soundcloud_song():
    song = Song.from_missing_data(
        url="https://open.spotify.com/track/0Ftrkz2waaHcjKb4qYvLmz",
        download_url="https://soundcloud.com/fredagain/delilah-pull-me-out-of-this",
    )

    assert not is_soundcloud_song(song)
