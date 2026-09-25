"""
Module for creating Song objects from SoundCloud URLs.

SoundCloud tracks are matched against Spotify so that they get the same
metadata as any other spotDL download. Tracks that can't be matched fall back
to the metadata available on SoundCloud. In both cases the audio is
downloaded from SoundCloud itself.
"""

import concurrent.futures
import logging
import re
from typing import Any, Dict, List, Optional, Union

import requests
from rapidfuzz import fuzz
from soundcloud import SoundCloud as SoundCloudClient
from soundcloud.resource.playlist import AlbumPlaylist, BasicAlbumPlaylist
from soundcloud.resource.track import BasicTrack, MiniTrack, Track
from soundcloud.resource.user import BasicUser

from spotdl.types.album import Album
from spotdl.types.playlist import Playlist
from spotdl.types.song import Song
from spotdl.utils.spotify import SpotifyClient

__all__ = [
    "SoundCloudError",
    "is_soundcloud_url",
    "is_soundcloud_song",
    "parse_soundcloud_url",
    "song_from_soundcloud_track",
    "match_spotify_song",
]

logger = logging.getLogger(__name__)
client = None  # pylint: disable=invalid-name

# Maximum number of track ids the SoundCloud API accepts in one request
TRACKS_CHUNK_SIZE = 50

# Number of threads used to match SoundCloud tracks against Spotify
MATCH_THREADS = 8

# User pages that resolve to the user's own uploads
USER_TRACK_PAGES = ["tracks", "popular-tracks"]

# Tags commonly added to SoundCloud titles that are not part of the song name
TITLE_NOISE_REGEX = re.compile(
    r"[\[\(][^\]\)]*(free|download|dl|out now|premiere|preview|clip)[^\]\)]*[\]\)]",
    re.IGNORECASE,
)

FEATURING_REGEX = re.compile(r"[\s([]+(?:feat\.?|ft\.?|featuring)\s+", re.IGNORECASE)
ARTIST_SPLIT_REGEX = re.compile(
    r"\s*,\s*|\s+x\s+|\s+(?:feat\.?|ft\.?|featuring)\s+", re.IGNORECASE
)


SCTrack = Union[Track, BasicTrack]
SCPlaylist = Union[AlbumPlaylist, BasicAlbumPlaylist]


class SoundCloudError(Exception):
    """
    Base class for all exceptions related to SoundCloud.
    """


def get_sc_client() -> SoundCloudClient:
    """
    Lazily initialize the SoundCloud client.

    ### Returns
    - the SoundCloud client
    """

    global client  # pylint: disable=global-statement
    if client is None:
        client = SoundCloudClient()

    return client


def is_soundcloud_url(url: Optional[str]) -> bool:
    """
    Check if the url points to SoundCloud.

    ### Arguments
    - url: the url to check

    ### Returns
    - True if the url is a SoundCloud url
    """

    return url is not None and "soundcloud.com/" in url


def is_soundcloud_song(song: Song) -> bool:
    """
    Check if the song was created from SoundCloud metadata
    (i.e. it wasn't matched to a Spotify track).

    ### Arguments
    - song: the song to check

    ### Returns
    - True if the song uses SoundCloud metadata
    """

    return is_soundcloud_url(song.url)


def normalize_url(url: str) -> str:
    """
    Normalize a SoundCloud url so that it can be resolved by the API.

    ### Arguments
    - url: the SoundCloud url

    ### Returns
    - the normalized url
    """

    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url

    # Follow short links (on.soundcloud.com/xxxx)
    if "on.soundcloud.com/" in url:
        url = requests.head(url, allow_redirects=True, timeout=10).url

    url = re.sub(
        r"^https?://(m\.|www\.)?soundcloud\.com", "https://soundcloud.com", url
    )

    # Remove query parameters (?si=..., ?utm_source=...) and trailing slashes
    return url.split("?", 1)[0].rstrip("/")


def get_cover_url(track: SCTrack) -> Optional[str]:
    """
    Get the highest quality artwork url for a track.

    ### Arguments
    - track: the SoundCloud track

    ### Returns
    - the artwork url, the uploader's avatar if the track has no artwork
    """

    cover_url = track.artwork_url or track.user.avatar_url
    if cover_url is None:
        return None

    # SoundCloud returns 100x100 images by default
    return cover_url.replace("-large.", "-t500x500.")


def get_track_url(track: SCTrack) -> str:
    """
    Get a url that can be used to download the track.
    Private tracks need the secret token in the url.

    ### Arguments
    - track: the SoundCloud track

    ### Returns
    - the track url
    """

    if track.secret_token:
        return f"{track.permalink_url}/{track.secret_token}"

    return track.permalink_url


def is_preview_only(track: SCTrack) -> bool:
    """
    Check if only a 30 second preview of the track is available
    (e.g. SoundCloud Go+ tracks).

    ### Arguments
    - track: the SoundCloud track

    ### Returns
    - True if only a preview is available
    """

    transcodings = track.media.transcodings
    return len(transcodings) > 0 and all(
        transcoding.snipped or "/preview/" in transcoding.url
        for transcoding in transcodings
    )


def split_title(title: str, username: str) -> Dict[str, Any]:
    """
    Split a SoundCloud title into song name and artists.
    Titles are often in the "Artist - Title" format when uploaded
    by labels or channels, otherwise the uploader is the artist.

    ### Arguments
    - title: the SoundCloud track title
    - username: the uploader's username

    ### Returns
    - dictionary with name and artists
    """

    title = TITLE_NOISE_REGEX.sub("", title).strip()

    if " - " in title:
        artist, name = [part.strip() for part in title.split(" - ", 1)]
    elif " – " in title:
        artist, name = [part.strip() for part in title.split(" – ", 1)]
    else:
        artist, name = username, title

    # Move "feat. X" from the song name to the artists
    featured: List[str] = []
    feat_match = FEATURING_REGEX.search(name)
    if feat_match:
        featured_part = name[feat_match.end() :].strip(" )]")
        name = name[: feat_match.start()].strip(" ([")
        featured = [a for a in ARTIST_SPLIT_REGEX.split(featured_part) if a]

    artists = [a.strip() for a in ARTIST_SPLIT_REGEX.split(artist) if a.strip()]
    for featured_artist in featured:
        if featured_artist not in artists:
            artists.append(featured_artist)

    return {"name": name or title, "artists": artists or [username]}


def song_from_soundcloud_track(
    track: SCTrack,
    playlist: Optional[SCPlaylist] = None,
    position: Optional[int] = None,
) -> Song:
    """
    Create a Song object from SoundCloud metadata.

    ### Arguments
    - track: the SoundCloud track
    - playlist: the album/set the track is part of
    - position: the track's position in the album/set

    ### Returns
    - the Song object
    """

    title_data = split_title(track.title, track.user.username)
    album = playlist if playlist is not None and playlist.is_album else None

    date = (track.release_date or track.display_date or "")[:10]
    if not date:
        date = track.created_at.strftime("%Y-%m-%d")

    return Song(
        name=title_data["name"],
        artists=title_data["artists"],
        artist=title_data["artists"][0],
        genres=[track.genre] if track.genre else [],
        disc_number=1,
        disc_count=1,
        album_name=album.title if album else title_data["name"],
        album_artist=album.user.username if album else title_data["artists"][0],
        duration=round(track.full_duration / 1000),
        year=int(date[:4]),
        date=date,
        track_number=position if album and position else 1,
        tracks_count=album.track_count if album else 1,
        song_id=str(track.id),
        explicit=False,
        publisher=track.label_name or track.user.username,
        url=track.permalink_url,
        isrc=None,
        cover_url=get_cover_url(track),
        copyright_text=None,
        download_url=get_track_url(track),
        popularity=None,
        album_id=str(album.id if album else track.id),
        artist_id=str(track.user.id),
        album_type="album" if album else "single",
    )


def clean_name(name: str) -> str:
    """
    Clean a song name for fuzzy comparison.

    ### Arguments
    - name: the song name

    ### Returns
    - the cleaned song name
    """

    name = TITLE_NOISE_REGEX.sub("", name).lower()
    name = FEATURING_REGEX.split(name, 1)[0]
    name = re.sub(r"[^\w\s]", " ", name)

    return " ".join(name.split())


def match_spotify_song(song: Song) -> Optional[Song]:
    """
    Find the Spotify track matching a song created from SoundCloud metadata.
    Only returns a result when the name, artist and duration all match
    so that SoundCloud-only songs (remixes, edits, sets) don't get wrong metadata.

    ### Arguments
    - song: the song created from SoundCloud metadata

    ### Returns
    - the Spotify song if a match was found, None otherwise
    """

    try:
        raw_results = SpotifyClient().search(f"{', '.join(song.artists)} - {song.name}")
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("Spotify search failed for %s: %s", song.display_name, exc)
        return None

    if raw_results is None:
        return None

    sc_name = clean_name(song.name)
    sc_artists = [artist.lower() for artist in song.artists]
    sc_album = clean_name(song.album_name) if song.album_type == "album" else None

    best_match = None
    best_score = (False, 0.0)
    for result in raw_results.get("tracks", {}).get("items", [])[:10]:
        if result is None or not result.get("id"):
            continue

        if abs(result["duration_ms"] / 1000 - song.duration) > 5:
            continue

        name_score = fuzz.ratio(clean_name(result["name"]), sc_name)
        if name_score < 85:
            continue

        artist_match = any(
            fuzz.ratio(artist["name"].lower(), sc_artist) >= 85
            for artist in result["artists"]
            for sc_artist in sc_artists
        )
        if not artist_match:
            continue

        # Prefer the version from the same album over singles/compilations
        album_match = sc_album is not None and (
            fuzz.ratio(clean_name(result.get("album", {}).get("name", "")), sc_album)
            >= 85
        )

        if (album_match, name_score) > best_score:
            best_match = result
            best_score = (album_match, name_score)

    if best_match is None:
        logger.debug("No Spotify match found for %s", song.display_name)
        return None

    try:
        spotify_song = Song.from_url(
            "https://open.spotify.com/track/" + best_match["id"]
        )
    except Exception as exc:  # pylint: disable=broad-except
        logger.debug("Failed to get Spotify song for %s: %s", song.display_name, exc)
        return None

    logger.debug("Matched %s to %s", song.download_url, spotify_song.url)

    return spotify_song


def create_song(
    track: SCTrack,
    playlist: Optional[SCPlaylist] = None,
    position: Optional[int] = None,
) -> Optional[Song]:
    """
    Create a Song object for a SoundCloud track, using Spotify metadata if
    the track can be matched.

    ### Arguments
    - track: the SoundCloud track
    - playlist: the album/set the track is part of
    - position: the track's position in the album/set

    ### Returns
    - the Song object, None if the track can't be downloaded
    """

    song = song_from_soundcloud_track(track, playlist, position)
    spotify_song = match_spotify_song(song)

    if is_preview_only(track):
        if spotify_song is None:
            logger.warning(
                "Skipping %s, only a 30 second preview is available on SoundCloud",
                track.permalink_url,
            )
            return None

        # Let the audio providers find the full song
        logger.info(
            "Only a preview of %s is available on SoundCloud, searching other providers",
            track.permalink_url,
        )
    elif spotify_song is not None:
        spotify_song.download_url = song.download_url

    if spotify_song is not None and not any(spotify_song.genres):
        spotify_song.genres = song.genres

    result = spotify_song or song
    result.list_position = position

    return result


def get_playlist_tracks(playlist: SCPlaylist) -> List[SCTrack]:
    """
    Get all tracks of a SoundCloud album/set in order.
    The API only returns full data for the first few tracks.

    ### Arguments
    - playlist: the SoundCloud album/set

    ### Returns
    - list of tracks
    """

    sc_client = get_sc_client()
    missing_ids = [
        track.id for track in playlist.tracks if isinstance(track, MiniTrack)
    ]

    fetched: Dict[int, SCTrack] = {}
    for index in range(0, len(missing_ids), TRACKS_CHUNK_SIZE):
        for track in sc_client.get_tracks(
            missing_ids[index : index + TRACKS_CHUNK_SIZE],
            playlistId=playlist.id,
            playlistSecretToken=playlist.secret_token,
        ):
            fetched[track.id] = track

    tracks: List[SCTrack] = []
    for playlist_track in playlist.tracks:
        full_track = (
            fetched.get(playlist_track.id)
            if isinstance(playlist_track, MiniTrack)
            else playlist_track
        )
        if full_track is None:
            logger.warning(
                "Could not get SoundCloud track %s, skipping", playlist_track.id
            )
            continue

        tracks.append(full_track)

    return tracks


def create_songs(
    tracks: List[SCTrack],
    playlist: Optional[SCPlaylist] = None,
) -> List[Song]:
    """
    Create Song objects for multiple SoundCloud tracks in parallel.

    ### Arguments
    - tracks: the SoundCloud tracks
    - playlist: the album/set the tracks are part of

    ### Returns
    - list of Song objects, in the same order as the tracks
    """

    with concurrent.futures.ThreadPoolExecutor(max_workers=MATCH_THREADS) as executor:
        results = executor.map(
            lambda args: create_song(args[1], playlist, args[0] + 1),
            enumerate(tracks),
        )

        return [song for song in results if song is not None]


def parse_soundcloud_url(url: str) -> Union[Song, Album, Playlist, None]:
    """
    Create a Song, Album or Playlist object from a SoundCloud url.

    ### Arguments
    - url: the SoundCloud track, album/set or user url

    ### Returns
    - Song for track urls (None if the track can't be downloaded),
    Album for albums, Playlist for sets and user profiles
    """

    url = normalize_url(url)

    # User pages like /popular-tracks can't be resolved, resolve the user instead
    parts = url.split("soundcloud.com/", 1)[-1].split("/")
    page = parts[1] if len(parts) == 2 and parts[1] in USER_TRACK_PAGES else ""
    resolve_url = url[: -len(page) - 1] if page else url

    resource = get_sc_client().resolve(resolve_url)
    if resource is None:
        raise SoundCloudError(f"Could not find anything on SoundCloud for: {url}")

    if isinstance(resource, (Track, BasicTrack)):
        return create_song(resource)

    if isinstance(resource, (AlbumPlaylist, BasicAlbumPlaylist)):
        tracks = get_playlist_tracks(resource)
        songs = create_songs(tracks, resource)
        if resource.is_album:
            return Album(
                name=resource.title,
                url=resource.permalink_url,
                urls=[song.url for song in songs],
                songs=songs,
                artist={"name": resource.user.username},
            )

        return Playlist(
            name=resource.title,
            url=resource.permalink_url,
            urls=[song.url for song in songs],
            songs=songs,
            description=resource.description or "",
            author_url=resource.user.permalink_url,
            author_name=resource.user.username,
            cover_url=(resource.artwork_url or "").replace("-large.", "-t500x500."),
        )

    if isinstance(resource, BasicUser):
        if resolve_url.lower() != resource.permalink_url.lower() and not page:
            raise SoundCloudError(
                f"Unsupported SoundCloud url: {url}. Only tracks, albums, "
                "sets and user profiles are supported."
            )

        sc_client = get_sc_client()
        user_tracks = (
            sc_client.get_user_popular_tracks(resource.id)
            if page == "popular-tracks"
            else sc_client.get_user_tracks(resource.id)
        )
        songs = create_songs(list(user_tracks))

        return Playlist(
            name=f"{resource.username} tracks",
            url=resource.permalink_url,
            urls=[song.url for song in songs],
            songs=songs,
            description="",
            author_url=resource.permalink_url,
            author_name=resource.username,
            cover_url=(resource.avatar_url or "").replace("-large.", "-t500x500."),
        )

    raise SoundCloudError(f"Unsupported SoundCloud url: {url}")
