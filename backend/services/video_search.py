from urllib.parse import quote

import yt_dlp

# YouTube search results param that sorts by upload date (newest first).
_SORT_BY_UPLOAD_DATE = "CAI%3D"


def search_youtube_videos(query: str, limit: int = 2) -> list[dict]:
    """Search YouTube for real videos matching a query, using yt-dlp's search
    extractor (no API key needed). Returns up to `limit` {title, url}
    dicts, sorted so the most recently uploaded videos come first. Returns
    an empty list on any failure rather than raising, since this is a
    "nice to have" enrichment step and shouldn't block the rest of the
    analysis.
    """
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "playlistend": limit,
    }

    search_url = f"https://www.youtube.com/results?search_query={quote(query)}&sp={_SORT_BY_UPLOAD_DATE}"

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(search_url, download=False)
    except Exception:
        return []

    entries = info.get("entries") or []
    results = []
    for entry in entries[:limit]:
        video_id = entry.get("id")
        title = entry.get("title")
        if not video_id or not title:
            continue
        results.append({"title": title, "url": f"https://www.youtube.com/watch?v={video_id}"})

    return results
