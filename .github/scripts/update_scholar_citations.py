from __future__ import annotations

import json
import re
import time
import unicodedata
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SCHOLAR_ID = "1PY8X28AAAAJ"
PROFILE_URLS = (
    f"https://scholar.google.com/citations?user={SCHOLAR_ID}&hl=en&pagesize=100",
    f"https://scholar.googleusercontent.com/citations?user={SCHOLAR_ID}&hl=en&pagesize=100",
)
PUBLICATIONS = {
    "dtsformer-citations.json": (
        "DTSFormer: Decoupled temporal-spatial diffusion transformer for enhanced "
        "long-term time series forecasting"
    ),
}


class ScholarProfileParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.statistics: list[str] = []
        self.publications: list[tuple[str, int]] = []
        self._capture_statistic = False
        self._in_publication = False
        self._capture_title = False
        self._capture_citations = False
        self._statistic_parts: list[str] = []
        self._title_parts: list[str] = []
        self._citation_parts: list[str] = []

    @staticmethod
    def _classes(attributes: list[tuple[str, str | None]]) -> set[str]:
        value = dict(attributes).get("class") or ""
        return set(value.split())

    def handle_starttag(self, tag: str, attributes: list[tuple[str, str | None]]) -> None:
        classes = self._classes(attributes)
        if tag == "td" and "gsc_rsb_std" in classes:
            self._capture_statistic = True
            self._statistic_parts = []
        elif tag == "tr" and "gsc_a_tr" in classes:
            self._in_publication = True
            self._title_parts = []
            self._citation_parts = []
        elif self._in_publication and tag == "a" and "gsc_a_at" in classes:
            self._capture_title = True
        elif self._in_publication and tag == "a" and "gsc_a_ac" in classes:
            self._capture_citations = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._capture_statistic:
            self.statistics.append("".join(self._statistic_parts).strip())
            self._capture_statistic = False
        elif tag == "a":
            self._capture_title = False
            self._capture_citations = False
        elif tag == "tr" and self._in_publication:
            title = "".join(self._title_parts).strip()
            citations = _integer("".join(self._citation_parts), default=0)
            if title:
                self.publications.append((title, citations))
            self._in_publication = False

    def handle_data(self, data: str) -> None:
        if self._capture_statistic:
            self._statistic_parts.append(data)
        if self._capture_title:
            self._title_parts.append(data)
        if self._capture_citations:
            self._citation_parts.append(data)


def _integer(value: str, default: int | None = None) -> int:
    digits = re.sub(r"[^0-9]", "", value)
    if digits:
        return int(digits)
    if default is not None:
        return default
    raise ValueError(f"Expected an integer, received {value!r}")


def _normalized_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _download_profile() -> str:
    headers = {
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
    }
    errors: list[str] = []
    for url in PROFILE_URLS:
        for attempt in range(2):
            try:
                with urlopen(Request(url, headers=headers), timeout=30) as response:
                    html = response.read().decode("utf-8", errors="replace")
                if "gsc_rsb_std" not in html or "gsc_a_tr" not in html:
                    raise ValueError("response did not contain a Scholar profile")
                return html
            except (HTTPError, URLError, TimeoutError, ValueError) as error:
                errors.append(f"{url} (attempt {attempt + 1}): {error}")
                time.sleep(2)
    raise RuntimeError("Unable to read Google Scholar:\n" + "\n".join(errors))


def _badge(label: str, citations: int) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "label": label,
        "message": str(citations),
        "color": "4285F4",
    }


def _write_badge(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = ScholarProfileParser()
    parser.feed(_download_profile())
    if len(parser.statistics) < 5:
        raise RuntimeError("Google Scholar citation metrics were not found")

    total_citations = _integer(parser.statistics[0])
    h_index = _integer(parser.statistics[2])
    i10_index = _integer(parser.statistics[4])
    indexed_publications = {
        _normalized_title(title): citations for title, citations in parser.publications
    }
    publication_citations: dict[str, int] = {}
    for filename, title in PUBLICATIONS.items():
        normalized = _normalized_title(title)
        if normalized not in indexed_publications:
            raise RuntimeError(f"Google Scholar publication was not found: {title}")
        publication_citations[filename] = indexed_publications[normalized]

    repository = Path(__file__).resolve().parents[2]
    _write_badge(
        repository / "scholar-citations.json",
        _badge("Google Scholar Citations", total_citations),
    )
    _write_badge(
        repository / "scholar-h-index.json",
        _badge("h-index", h_index),
    )
    _write_badge(
        repository / "scholar-i10-index.json",
        _badge("i10-index", i10_index),
    )
    for filename, citations in publication_citations.items():
        _write_badge(repository / filename, _badge("Citations", citations))

    details = ", ".join(
        f"{filename}={citations}"
        for filename, citations in publication_citations.items()
    )
    print(
        "Google Scholar metrics: "
        f"citations={total_citations}, h-index={h_index}, i10-index={i10_index}, "
        f"{details}"
    )


if __name__ == "__main__":
    main()
