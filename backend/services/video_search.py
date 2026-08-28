import yt_dlp


def search_youtube_videos(query: str, limit: int = 2) -> list[dict]:
    """Search YouTube for real videos matching a query, using yt-dlp's search
    extractor (no API key needed). Returns up to `limit` {title, url}
    dicts in YouTube's own relevance-ranked order. Returns an empty list on
    any failure rather than raising, since this is a "nice to have" enrichment
    step and shouldn't block the rest of the analysis.
    """
    options = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(f"ytsearch{limit}:{query}", download=False)
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
