# SpotifyToYouTubeMusic

SpotifyToYouTubeMusic is a free, open-source tool for moving Spotify playlists
to YouTube Music. It runs on your own computer against your own accounts.

> ### A fork of SpotTransfer
>
> **This project is a fork of [SpotTransfer](https://github.com/Pushan2005/SpotTransfer)
> by [Pushan2005](https://github.com/Pushan2005), and uses it as its basis.**
> All of the original work and design that SpotTransfer is built
> around belong to that project and its contributors.
>
> This fork keeps that foundation and extends it, focusing on the self-hosted
> command-line path for large libraries:
>
> - **Whole-library listing** — `list_playlists.py` reads every playlist in
>   your Spotify account into a reviewable `playlists.csv`, paging through the
>   library so accounts with thousands of saved items are listed in full.
> - **Bulk transfers** — many playlists in one run, from that reviewed file.
> - **Resume after expiry** — YouTube Music credentials expire mid-run on large
>   libraries; the transfer saves its place and picks up exactly where it left off.
> - **Forgiving credential input** — paste a cURL command, raw headers, or a HAR.
> - **Renamed credential file** — `browser.json` is now `youtubemusic.json`, and
>   it is git-ignored rather than tracked, so a live Google session cannot be
>   committed by accident.
>
> If you want the hosted web app instead of a local script, use the original
> project. Please send stars and thanks upstream.

---

## Contents

- [Install](#install)
- [Step 1 - YouTube Music credentials](#step-1---youtube-music-credentials)
- [Step 2 - Pick your playlists](#step-2---pick-your-playlists)
- [Step 3 - Run the transfer](#step-3---run-the-transfer)
- [If the transfer stops](#if-the-transfer-stops)
- [Keep your credentials out of git](#keep-your-credentials-out-of-git)
- [Known limits](#known-limits)
- [Troubleshooting](#troubleshooting)

---

## Install

**Prerequisites:** Python 3.8+

Copy and paste, one block at a time:

```bash
git clone https://github.com/ynegve/SpotifyToYouTubeMusic.git
cd SpotifyToYouTubeMusic/backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

On Windows, replace `source venv/bin/activate` with:

```bash
venv\Scripts\activate
```

Every command below assumes you are in the `backend` directory with the virtual
environment activated. Your prompt should start with `(venv)`.

---

## Step 1 - YouTube Music credentials

This tells the script it is allowed to create playlists on your account.

1. Create `backend/youtubemusic.json` by copying the example:

   ```bash
   cp youtubemusic.json.example youtubemusic.json
   ```

2. Open [music.youtube.com](https://music.youtube.com) and **sign in**.
3. Press **F12** to open developer tools, then click the **Network** tab.
4. In the filter box, type `browse`.
5. Reload the page. A list of requests appears.
6. Click a `browse` request whose **Status** is `200` and **Method** is `POST`.
7. Copy it:
   - **Chrome / Edge:** right-click the request → **Copy** → **Copy as cURL**
   - **Firefox:** right-click the request → **Copy Value** → **Copy as cURL**
8. Open `backend/youtubemusic.json`, delete everything in it, paste, and **save**.

> **Chrome's "Export HAR" does not work here.** Chrome strips the `cookie` and
> `authorization` headers out of HAR exports by default, so the file arrives
> with no credentials in it. Use **Copy as cURL** instead. If you prefer HAR,
> tick **Allow to generate HAR with sensitive data** in the developer tools
> settings (F1 → Preferences → Network) first.

`youtubemusic.json` accepts any of these, so paste whichever your browser gives
you. It does not have to be valid JSON when you paste it; the first run
converts whatever you pasted into the normalized form shown in
`youtubemusic.json.example`.

| Format | Where it comes from |
| --- | --- |
| cURL command | **Copy as cURL** (recommended) |
| Raw request headers | **Copy Request Headers**, or the **Raw** toggle in the Headers tab |
| HAR | **Copy as HAR (with sensitive data)** |

---

## Step 2 - Pick your playlists

Two options. Use **2A** to move your whole library; use **2B** for one or two
playlists.

### 2A - Transfer many playlists (review a list first)

**First, give the script read access to your Spotify library.**

1. Open [open.spotify.com](https://open.spotify.com) and **sign in**.
2. Press **F12**, then open the **Application** tab (**Storage** in Firefox).
3. In the sidebar, expand **Cookies** and click `https://open.spotify.com`.
4. Find the row named `sp_dc` and copy its **Value**.
5. Create `backend/spotify.json` by copying the example:

   ```bash
   cp spotify.json.example spotify.json
   ```

6. Open `backend/spotify.json` and fill in both fields:

   ```json
   {
       "identifier": "your-spotify-email@example.com",
       "cookies": "sp_dc=PASTE_THE_VALUE_YOU_COPIED"
   }
   ```

**Now list your playlists:**

```bash
python3 list_playlists.py
```

This pages through your entire Spotify library, printing its progress, and
writes `backend/playlists.csv`, one playlist per row:

```csv
name,playlist_id
Café con Leche,37i9dQZF1DXa3NnZWk6Z3T
Road Trip,3ydrYAjx0aICD9neZbtPs7
Focus,1aaaaaaaaaaaaaaaaaaaaa
```

**Review it.** Open `playlists.csv` in a text editor or a spreadsheet, **delete
the rows for playlists you do not want**, and save. Keep the `name,playlist_id`
header row. Whatever is left is what gets transferred.

The reader is deliberately forgiving: blank rows, extra columns, re-ordered
columns, a deleted header, `#` at the start of a row to skip it, a full
playlist URL in place of an ID, and spreadsheet re-saves (CRLF, Excel BOM) all
work.

### 2B - Transfer one or two playlists

Skip `playlists.csv` entirely and edit `backend/setup.py`:

```python
spotify_playlist_link = "https://open.spotify.com/playlist/your-playlist-id"
```

Or a list, transferred in the order given:

```python
spotify_playlist_link = [
    "https://open.spotify.com/playlist/first-playlist-id",
    "https://open.spotify.com/playlist/second-playlist-id",
]
```

> If `playlists.csv` exists and has at least one row, it wins and `setup.py` is
> ignored. Delete `playlists.csv` to go back to using `setup.py`.

---

## Step 3 - Run the transfer

```bash
python3 selfhost.py
```

The script prints which source it is using, then works through the playlists
one at a time, showing a progress bar per playlist. Each playlist is created on
YouTube Music as **private**.

When it finishes it lists every playlist it created, plus any tracks it could
not find on YouTube Music.

---

## If the transfer stops

YouTube Music credentials expire after a while, which you will notice on large
libraries. When that happens the script **stops safely**, saves its place in
`backend/transfer_progress.json`, and tells you what to do:

1. Redo [Step 1](#step-1---youtube-music-credentials) to get fresh credentials.
2. Delete everything in `backend/youtubemusic.json`, paste the new copy, and **save**.
3. Run `python3 selfhost.py` again.

It resumes exactly where it stopped. Playlists already created are **not**
created again, and tracks already searched are **not** searched again.

Changing which playlists you want (editing `playlists.csv` or `setup.py`)
discards the saved progress and starts fresh.

---

## Keep your credentials out of git

`youtubemusic.json` holds a live Google session and `spotify.json` holds a live
Spotify session. Anyone with those files can sign in as you.

Both are listed in `.gitignore`, along with `playlists.csv` and
`transfer_progress.json`. Only the `.example` files are tracked. Nothing you
have to do — but never paste the contents of either real file into an issue, a
pull request, or a chat.

> **Upgrading from SpotTransfer?** Upstream tracks `browser.json` in git and
> asks you to run `git update-index --skip-worktree` on it. This fork renames
> that file to `youtubemusic.json` and git-ignores it instead, so that step is
> gone. Rename your existing file and you are done:
>
> ```bash
> mv backend/browser.json backend/youtubemusic.json
> ```

---

## Known limits

- **Matching is a search, not a lookup.** Tracks are found on YouTube Music by
  searching for the title and artist, so a wrong match or a miss is possible.
  Anything not found is listed at the end of the run. Nothing is deleted from
  Spotify, so a bad result costs you only the new YouTube Music playlist.
- **Both services are read through private APIs.** Spotify is read via
  [SpotAPI](https://github.com/Aran404/SpotAPI) and YouTube Music via
  [ytmusicapi](https://github.com/sigma67/ytmusicapi). Neither is an official,
  supported interface, so either service can change it without notice and break
  this tool until the dependency catches up.
- **YouTube Music credentials expire mid-run.** Expected on large libraries;
  see [If the transfer stops](#if-the-transfer-stops).
- **Local files, podcasts, and unavailable tracks are skipped.** They carry too
  little metadata to search for. The count is reported per playlist.
- **A playlist that Spotify refuses to page through fully is reported, not
  hidden.** If Spotify returns fewer tracks than the playlist's own stated
  total, the run prints a warning naming both numbers rather than silently
  transferring a partial playlist.

---

## Troubleshooting

| Message | Fix |
| --- | --- |
| `youtubemusic.json is a HAR export whose requests carry no cookie header` | Chrome sanitized the HAR. Use **Copy as cURL** (Step 1). |
| `Parsed youtubemusic.json is missing the authorization header` | You copied only part of the request. Copy the whole thing again. |
| `The "cookies" value in spotify.json does not contain sp_dc` | Copy the `sp_dc` cookie value, not the cookie name or another cookie. |
| `playlists.csv row 4 has an invalid Spotify playlist ID` | That row was edited badly. Fix or delete the row. |
| `playlists.csv lists no playlists` | You deleted every row. Regenerate it or delete the file. |
| `Edit spotify_playlist_link before running the script` | `setup.py` still has the placeholder in it. |
| `cannot import name 'spotify_playlist_link' from 'setup'` | `setup.py` lost its `spotify_playlist_link = ""` line. Add it back. |
| `ModuleNotFoundError` | The virtual environment is not active. Run `source venv/bin/activate`. |

---

# Acknowledgements

- [Pushan2005](https://github.com/Pushan2005) and the
  [SpotTransfer](https://github.com/Pushan2005/SpotTransfer) contributors, whose
  project this is a fork of and is built on.
- [Aran404](https://github.com/Aran404/) for SpotAPI.
- [sigma67](https://github.com/sigma67) for ytmusicapi.

# Legal Notice

> **Disclaimer**: This repository and any associated code are provided "as is" without warranty of any kind, either expressed or implied. The author of this repository does not accept any responsibility for the use or misuse of this repository or its contents. The author does not endorse any actions or consequences arising from the use of this repository. Any copies, forks, or re-uploads made by other users are not the responsibility of the author. The repository is solely intended as a Proof Of Concept for educational purposes regarding the use of a service's private API. By using this repository, you acknowledge that the author makes no claims about the accuracy, legality, or safety of the code and accepts no liability for any issues that may arise. More information can be found [HERE](./LEGAL_NOTICE.md).
