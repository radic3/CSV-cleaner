import re
import urllib.parse
from typing import Optional


def _strip_locale_and_prefixes(path: str) -> str:
    path = re.sub(r"^/+", "", path)
    parts = path.split("/")
    if parts and parts[0] in {"it", "en"}:
        parts = parts[1:]
    drop_prefixes = {"blog", "articoli", "articles"}
    while parts and parts[0] in drop_prefixes:
        parts = parts[1:]
    return "/".join(parts)


def _last_segment(path: str) -> str:
    path = re.sub(r"[?#].*$", "", path)
    path = re.sub(r"/+$", "", path)
    path = re.sub(r"\.html?$", "", path, flags=re.IGNORECASE)
    if not path:
        return ""
    seg = path.split("/")[-1]
    return seg


def _clean_slug_text(text: str) -> str:
    text = text.replace("_", "-")
    text = re.sub(r"%[0-9A-Fa-f]{2}", lambda m: urllib.parse.unquote(m.group(0)), text)
    text = urllib.parse.unquote(text)
    text = re.sub(r"[\-\u2013\u2014]+", " ", text)
    text = re.sub(r"[\(\)\[\]{}\.,;:!\?\"\u201c\u201d\u2019'`]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _sentence_case(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    lowered = text.lower()
    return lowered[0].upper() + lowered[1:]


def extract_article_title(url_or_path: Optional[str]) -> str:
    """Extract a human-friendly article title from a URL or path.

    Rules:
    - Use last path segment (after removing locale like /it/ or /en/ and common prefixes like blog/articoli)
    - Remove extension, query, fragment
    - Replace dashes/underscores/punctuation with spaces
    - Decode percent-encodings
    - Apply sentence case (e.g., "la-nuova-stable-coin-europea" -> "La nuova stable coin europea")
    """
    s = (url_or_path or "").strip()
    if not s:
        return ""
    parsed = urllib.parse.urlparse(s)
    path = parsed.path if parsed.scheme or parsed.netloc else s
    path = _strip_locale_and_prefixes(path)
    seg = _last_segment(path)
    cleaned = _clean_slug_text(seg)
    titled = _sentence_case(cleaned)
    return titled


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Extract human title from URL/path")
    ap.add_argument("--url", required=True, help="URL or path to extract title from")
    args = ap.parse_args()
    print(extract_article_title(args.url))


