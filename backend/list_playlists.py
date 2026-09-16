"""List every Spotify playlist in your library into a reviewable text file.

Run this before ``selfhost.py`` when you want to transfer many playlists at
once:

1. Put your Spotify session cookies in ``spotify.json``
   (copy ``spotify.json.example`` and fill it in).
2. Run ``python3 list_playlists.py``; it writes ``playlists.csv``.
3. Open ``playlists.csv``, delete the rows for playlists you do not want,
   and save the file.
4. Run ``python3 selfhost.py``; it transfers whatever is left in the file.

``playlists.csv`` has one playlist per row as ``name,playlist_id``, so
reviewing it means deleting whole rows, in a text editor or a spreadsheet.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from collections.abc import Mapping
from pathlib import Path

from spotapi import Config, Login, NoopLogger, PrivatePlaylist


BASE_DIR = Path(__file__).resolve().parent
SPOTIFY_AUTH_PATH = BASE_DIR / "spotify.json"
PLAYLISTS_PATH = BASE_DIR / "playlists.csv"

_PLAYLIST_URI_PREFIX = "spotify:playlist:"
# playlists.csv columns, in order. The name comes first so the file is
# readable at a glance and sorts naturally in a spreadsheet.
CSV_COLUMNS = ("name", "playlist_id")
# Spotify caps a libraryV3 page at the requested limit and returns the real
# size in totalCount, so the library has to be walked page by page. 500 is the
# largest page size observed to come back intact.
_LIBRARY_PAGE_SIZE = 500


def _playlist_name(node: Mapping[str, object]) -> str:
    """Pull a display name out of a playlist node, whatever shape it has."""

    for key in ("name", "title"):
        value = node.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    # Some responses nest the human-readable fields one level down.
    for key in ("attributes", "data", "playlist"):
        nested = node.get(key)
        if isinstance(nested, Mapping):
            name = _playlist_name(nested)
            if name != "Untitled playlist":
                return name

    return "Untitled playlist"


def _collect_playlists(
    node: object,
    found: list[dict[str, str]],
    seen: set[str],
) -> None:
    """Walk a GraphQL response and collect every playlist it mentions.

    Spotify's private library response nests playlists differently depending
    on folders and account features, so the whole payload is searched for
    playlist URIs rather than following one fixed path that could break.
    """

    if isinstance(node, Mapping):
        uri = node.get("uri")
        if isinstance(uri, str) and uri.startswith(_PLAYLIST_URI_PREFIX):
            playlist_id = uri[len(_PLAYLIST_URI_PREFIX) :].strip()
            if playlist_id and playlist_id not in seen:
                seen.add(playlist_id)
                found.append({"id": playlist_id, "name": _playlist_name(node)})

        for value in node.values():
            _collect_playlists(value, found, seen)

    elif isinstance(node, list):
        for value in node:
            _collect_playlists(value, found, seen)


def load_spotify_login() -> Login:
    """Build a logged-in SpotAPI session from the cookies in spotify.json."""

    if not SPOTIFY_AUTH_PATH.is_file():
        raise FileNotFoundError(
            f"Could not find {SPOTIFY_AUTH_PATH.name}. Copy "
            "spotify.json.example to spotify.json and fill in your Spotify "
            "account email and session cookies."
        )

    try:
        data = json.loads(SPOTIFY_AUTH_PATH.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{SPOTIFY_AUTH_PATH.name} is not valid JSON. It must look like "
            '{"identifier": "you@example.com", "cookies": "sp_dc=..."}'
        ) from error

    if not isinstance(data, Mapping):
        raise ValueError(f"{SPOTIFY_AUTH_PATH.name} must contain a JSON object")

    identifier = data.get("identifier")
    cookies = data.get("cookies")

    if not isinstance(identifier, str) or not identifier.strip():
        raise ValueError(
            f'Set "identifier" in {SPOTIFY_AUTH_PATH.name} to the email address '
            "or username of your Spotify account"
        )
    if not isinstance(cookies, (str, Mapping)) or not cookies:
        raise ValueError(
            f'Set "cookies" in {SPOTIFY_AUTH_PATH.name} to the cookie string '
            "copied from an open.spotify.com request"
        )

    cookie_text = cookies if isinstance(cookies, str) else ";".join(cookies)
    if "sp_dc" not in cookie_text:
        raise ValueError(
            f'The "cookies" value in {SPOTIFY_AUTH_PATH.name} does not contain '
            "sp_dc, which is the cookie that proves you are logged in. Copy the "
            "whole cookie header from open.spotify.com and try again."
        )

    return Login.from_cookies(
        {"identifier": identifier.strip(), "cookies": cookies},
        Config(logger=NoopLogger()),
    )


def _library_node(page: object) -> Mapping[str, object]:
    """Return the libraryV3 node of a response, or an empty mapping."""

    node: object = page
    for key in ("data", "me", "libraryV3"):
        if not isinstance(node, Mapping):
            return {}
        node = node.get(key)
    return node if isinstance(node, Mapping) else {}


def _library_page(
    library: PrivatePlaylist,
    limit: int,
    offset: int,
) -> Mapping[str, object]:
    """Fetch one page of the library.

    ``PrivatePlaylist.get_library`` hardcodes ``offset: 0``, so on its own it
    can only ever see the first page and silently drops every playlist past
    it. The same query is reissued here with the offset filled in. The
    persisted-query hash and the HTTP client are SpotAPI's own, so this keeps
    following SpotAPI when it updates them.
    """

    url = "https://api-partner.spotify.com/pathfinder/v1/query"
    params = {
        "operationName": "libraryV3",
        "variables": json.dumps(
            {
                "filters": [],
                "order": None,
                "textFilter": "",
                "features": ["LIKED_SONGS", "YOUR_EPISODES", "PRERELEASES"],
                "limit": limit,
                "offset": offset,
                "flatten": False,
                "expandedFolders": [],
                "folderUri": None,
                "includeFoldersWhenFlattening": True,
            }
        ),
        "extensions": json.dumps(
            {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": library.base.part_hash("libraryV3"),
                }
            }
        ),
    }

    response = library.login.client.post(url, params=params, authenticate=True)
    if response.fail:
        raise RuntimeError(
            f"Could not read your Spotify library: {response.error.string}"
        )
    return response.response


def fetch_library_playlists(login: Login) -> list[dict[str, str]]:
    """Return every playlist in the logged-in account's library.

    The library holds albums, artists and podcasts alongside playlists, so the
    page counts below are library entries rather than playlists; only a subset
    of each page turns into a row in playlists.csv.
    """

    library = PrivatePlaylist(login)

    found: list[dict[str, str]] = []
    seen: set[str] = set()
    offset = 0
    total = 0

    while True:
        node = _library_node(_library_page(library, _LIBRARY_PAGE_SIZE, offset))
        items = node.get("items")
        if not isinstance(items, list) or not items:
            break

        _collect_playlists(items, found, seen)

        total_count = node.get("totalCount")
        if isinstance(total_count, int) and total_count > total:
            total = total_count

        # Advance by what the server actually returned rather than by the
        # requested limit, so a short page cannot skip over entries.
        offset += len(items)
        print(f"  scanned {min(offset, total)}/{total} library entries")

        if offset >= total:
            break

    if not found:
        raise RuntimeError(
            "No playlists were found in your Spotify library. If you do have "
            "playlists, your session cookies have probably expired; copy a "
            f"fresh set into {SPOTIFY_AUTH_PATH.name} and try again."
        )

    return found


def render_playlists_file(playlists: list[dict[str, str]]) -> str:
    """Render the reviewable playlists.csv contents.

    Written with the csv module because playlist names routinely contain
    commas and quotes, which a hand-rolled join would corrupt.
    """

    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)

    for playlist in playlists:
        # Collapse any newlines so one playlist always occupies one row.
        name = " ".join(playlist["name"].split())
        writer.writerow([name, playlist["id"]])

    return buffer.getvalue()


def main() -> int:
    try:
        login = load_spotify_login()
        print("Fetching your Spotify library...")
        playlists = fetch_library_playlists(login)
    except Exception as error:
        print(f"Could not list your playlists: {error}", file=sys.stderr)
        return 1

    if PLAYLISTS_PATH.exists():
        backup = PLAYLISTS_PATH.with_name(PLAYLISTS_PATH.name + ".previous")
        # Never silently discard a list the user may have already edited.
        backup.write_text(PLAYLISTS_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"Kept your previous list as {backup.name}")

    PLAYLISTS_PATH.write_text(
        render_playlists_file(playlists), encoding="utf-8", newline=""
    )

    print(f"Wrote {len(playlists)} playlist(s) to {PLAYLISTS_PATH.name}")
    print()
    print("Next steps:")
    print(f"  1. Open {PLAYLISTS_PATH.name}")
    print("  2. Delete the rows for playlists you do NOT want to transfer")
    print("  3. Save the file")
    print("  4. Run: python3 selfhost.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
