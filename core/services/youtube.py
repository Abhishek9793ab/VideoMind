
import re
from urllib.parse import urlparse, parse_qs

from youtube_transcript_api import YouTubeTranscriptApi


def extract_video_id(url):
    """Extract the 11-character YouTube video ID from supported URLs."""
    url = (url or "").strip()

    if not url:
        raise ValueError("Please enter a YouTube video URL.")

    # Allow a raw 11-character video ID as well.
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url

    try:
        parsed = urlparse(url if "://" in url else "https://" + url)
        host = parsed.netloc.lower().split(":")[0]
        path_parts = [part for part in parsed.path.split("/") if part]

        if host in ("youtu.be", "www.youtu.be"):
            video_id = path_parts[0] if path_parts else ""

        elif host in (
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
        ):
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [""])[0]
            elif len(path_parts) >= 2 and path_parts[0] in (
                "shorts", "embed", "live"
            ):
                video_id = path_parts[1]
            else:
                video_id = ""
        else:
            video_id = ""

    except (ValueError, AttributeError):
        video_id = ""

    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError(
            "Invalid YouTube URL. Use a standard video, Shorts, "
            "or youtu.be link."
        )

    return video_id


def stamp(seconds):
    """Convert seconds to MM:SS or HH:MM:SS."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    return f"{minutes:02d}:{seconds:02d}"


def fetch_transcript(video_id):
    """
    Fetch captions using available transcript languages.
    Prefer English, then Hindi, then other available languages.
    """
    api = YouTubeTranscriptApi()

    try:
        transcript_list = api.list(video_id)
    except Exception as exc:
        raise ValueError(
            "Could not retrieve YouTube captions. The video may have "
            "captions disabled, be restricted, or be temporarily "
            f"unavailable. Details: {exc}"
        ) from exc

    available = []

    try:
        for transcript in transcript_list:
            available.append(transcript)
    except Exception as exc:
        raise ValueError(
            f"Could not list available captions: {exc}"
        ) from exc

    if not available:
        raise ValueError(
            "No captions are available for this video."
        )

    # Prefer English, then Hindi, then other available languages.
    def language_priority(transcript):
        code = getattr(transcript, "language_code", "")
        generated = getattr(transcript, "is_generated", False)

        if code == "en":
            language_rank = 0
        elif code.startswith("en-"):
            language_rank = 1
        elif code == "hi":
            language_rank = 2
        elif code.startswith("hi-"):
            language_rank = 3
        else:
            language_rank = 4

        # Prefer manually created captions when language is equal.
        return (language_rank, bool(generated))

    available.sort(key=language_priority)

    errors = []

    for transcript_option in available:
        try:
            fetched = transcript_option.fetch()
            result = []

            for item in fetched:
                if isinstance(item, dict):
                    text = str(item.get("text", "")).strip()
                    start = float(item.get("start", 0) or 0)
                    duration = float(item.get("duration", 0) or 0)
                else:
                    text = str(getattr(item, "text", "")).strip()
                    start = float(getattr(item, "start", 0) or 0)
                    duration = float(getattr(item, "duration", 0) or 0)

                if text:
                    result.append({
                        "text": text.replace("\n", " "),
                        "start": start,
                        "end": start + duration,
                        "timestamp": stamp(start),
                    })

            if result:
                return result

            errors.append(
                f"{getattr(transcript_option, 'language_code', 'unknown')}: "
                "transcript was empty"
            )

        except Exception as exc:
            language = getattr(
                transcript_option, "language_code", "unknown"
            )
            errors.append(f"{language}: {exc}")

    raise ValueError(
        "Captions were listed, but none could be fetched successfully. "
        "Try another video with accessible captions. "
        + " | ".join(errors[:3])
    )
