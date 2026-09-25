
<!--- mdformat-toc start --slug=github --->

<!---
!!! IF EDITING THE README, MOST CHANGES SHOULD ALSO BE PROPAGATED TO index.md in `/docs/`.
!!! ADJUST FORMATTING THERE AS NEEDED, AND REMOVE README-ONLY / ReadTheDocs REFERENCES.
--->

<div align="center">

# spotDL v4

**spotDL** finds songs from Spotify playlists on YouTube and downloads them - along with album art, lyrics and metadata.

[![MIT License](https://img.shields.io/github/license/spotdl/spotify-downloader?color=44CC11&style=flat-square)](https://github.com/spotDL/spotify-downloader/blob/master/LICENSE)
[![PyPI version](https://img.shields.io/pypi/pyversions/spotDL?color=%2344CC11&style=flat-square)](https://pypi.org/project/spotdl/)
[![PyPi downloads](https://img.shields.io/pypi/dw/spotDL?label=downloads@pypi&color=344CC11&style=flat-square)](https://pypi.org/project/spotdl/)
![GitHub Repo stars](https://img.shields.io/github/stars/spotDL/spotify-downloader)
![Contributors](https://img.shields.io/github/contributors/spotDL/spotify-downloader?style=flat-square)
[![Discord](https://img.shields.io/discord/771628785447337985?label=discord&logo=discord&style=flat-square)](https://discord.gg/xCa23pwJWY)

> spotDL: The fastest, easiest and most accurate command-line music downloader.
</div>

______________________________________________________________________
**[Read the documentation on ReadTheDocs!](https://spotdl.readthedocs.io)**
______________________________________________________________________

> **This is a fork of [spotDL/spotify-downloader](https://github.com/spotDL/spotify-downloader) that adds SoundCloud support.**
> Pass SoundCloud track, album, playlist or profile URLs to the same `spotdl` command and get the same metadata and output formats as Spotify downloads.
> See [SoundCloud](#soundcloud) below.
>
> Install this fork with:
>
> ```sh
> pip install git+https://github.com/swhelan123/spotify-downloader.git
> ```

## Installation

Refer to our [Installation Guide](docs/installation.md) for more details.

### Python (Recommended Method)

- _spotDL_ can be installed by running `pip install spotdl`.
- To update spotDL run `pip install --upgrade spotdl`

  > On some systems you might have to change `pip` to `pip3`.

<details>
    <summary style="font-size:1.25em"><strong>Other options</strong></summary>

- Prebuilt executable
  - You can download the latest version from the
    [Releases Tab](https://github.com/spotDL/spotify-downloader/releases)
- On Termux
  - `curl -L https://raw.githubusercontent.com/spotDL/spotify-downloader/master/scripts/termux.sh | sh`
- Arch
  - There is an [Arch User Repository (AUR) package](https://aur.archlinux.org/packages/spotdl/) for
    spotDL.
- Docker
  - Build image:

    ```bash
    docker build -t spotdl .
    ```

  - Launch container with spotDL parameters (see section below). You need to create mapped
    volume to access song files

    ```bash
    docker run --rm -v $(pwd):/music spotdl download [trackUrl]
    ```

  - For Docker Compose and permission-managed Docker downloads, see
    [the Docker section in `/docs/index.md`](docs/index.md#docker).

  - Build from source

    ```bash
    git clone https://github.com/spotDL/spotify-downloader && cd spotify-downloader
    pip install uv
    uv sync
    uv run scripts/build.py
    ```

    An executable is created in `spotify-downloader/dist/`.

</details>

### Installing FFmpeg

FFmpeg is required for spotDL. If using FFmpeg only for spotDL, you can simply install FFmpeg to your spotDL installation directory:
`spotdl --download-ffmpeg`

We recommend the above option, but if you want to install FFmpeg system-wide,
follow these instructions

- [Windows Tutorial](https://windowsloop.com/install-ffmpeg-windows-10/)
- OSX - `brew install ffmpeg`
- Linux - `sudo apt install ffmpeg` or use your distro's package manager

### Installing Deno

We strongly recommend installing Deno. spotDL uses yt-dlp for YouTube downloads, and some
videos require Deno to download successfully. Without Deno, spotDL may fail to download some
songs, including videos marked as "made for kids".

If using Deno only for spotDL, install Deno to your spotDL directory:
`spotdl --download-deno`

If you want to install Deno system-wide instead, follow the
[official Deno installation guide](https://docs.deno.com/runtime/getting_started/installation/).

## Usage

Using SpotDL without options:

```sh
spotdl [urls]
```

You can run _spotDL_ as a package if running it as a script doesn't work:

```sh
python -m spotdl [urls]
```

General usage:

```sh
spotdl [operation] [options] QUERY
```

There are different **operations** spotDL can perform. The _default_ is `download`, which simply downloads the songs from YouTube and embeds metadata.

The **query** for spotDL is usually a list of Spotify URLs, but for some operations like **sync**, only a single link or file is required.
For a list of all **options** use ```spotdl -h```

<details>
<summary style="font-size:1em"><strong>Supported operations</strong></summary>

- `save`: Saves only the metadata from Spotify without downloading anything.
    - Usage:
        `spotdl save [query] --save-file {filename}.spotdl`

- `web`: Starts a web interface instead of using the command line. However, it has limited features and only supports downloading individual songs.

- `url`: Get user-friendly URL for each song from the query.
    - Usage:
        `spotdl url [query]`

- `sync`: Updates directories. Compares the directory with the current state of the playlist. Newly added songs will be downloaded and removed songs will be deleted. No other songs will be downloaded and no other files will be deleted.

    - Usage:
        `spotdl sync [query] --save-file {filename}.spotdl`

        This creates a new **sync** file. To update the directory in the future, use:

        `spotdl sync {filename}.spotdl`

- `meta`: Updates metadata for the provided song files.

</details>

### SoundCloud

SoundCloud URLs work anywhere a Spotify URL does:

```sh
spotdl download https://soundcloud.com/fredagain/delilah-pull-me-out-of-this
```

Supported URLs:

- Tracks: `https://soundcloud.com/{user}/{track}` (private links with a secret token work too)
- Albums and playlists: `https://soundcloud.com/{user}/sets/{name}`
- All tracks of a user: `https://soundcloud.com/{user}`, `/tracks` or `/popular-tracks`
- Mobile (`m.soundcloud.com`), short (`on.soundcloud.com`) and share links with `?si=...` parameters

How metadata works:

- Each track is matched against Spotify. A match only counts if the name, artist and duration (within 5 seconds) all agree, so the song gets the same tags as a Spotify download: album, track number, label, cover art, lyrics and so on. Inside a SoundCloud album, the album version is preferred over singles.
- Tracks that aren't on Spotify (remixes, edits, unreleased tracks, DJ sets) are tagged using SoundCloud's own data: the artist and title parsed from "Artist - Title", featured artists, genre, label, release date and 500x500 artwork.

Audio is downloaded from SoundCloud. Many major-label tracks on SoundCloud are DRM protected or only offer a 30 second preview; if such a track was matched to Spotify, spotDL searches the usual audio providers (YouTube Music, YouTube, ...) instead. Unmatched tracks that are DRM protected or preview-only can't be downloaded.

## Music Sourcing and Audio Quality

spotDL uses YouTube as a source for music downloads. This method is used to avoid any issues related to downloading music from Spotify.

> **Note**
> Users are responsible for their actions and potential legal consequences. We do not support unauthorized downloading of copyrighted material and take no responsibility for user actions.

### Audio Quality

spotDL downloads music from YouTube and is designed to always download the highest possible bitrate; which is 128 kbps for regular users and 256 kbps for YouTube Music premium users.

Check the [Audio Formats](docs/usage.md#audio-formats-and-quality) page for more info.

## Contributing

Interested in contributing? Check out our [CONTRIBUTING.md](docs/CONTRIBUTING.md) to find
resources around contributing along with a guide on how to set up a development environment.

### Join our amazing community as a code contributor

<a href="https://github.com/spotDL/spotify-downloader/graphs/contributors">
  <img class="dark-light" src="https://contrib.rocks/image?repo=spotDL/spotify-downloader&anon=0&columns=25&max=100&r=true" />
</a>

## License

This project is Licensed under the [MIT](/LICENSE) License.
