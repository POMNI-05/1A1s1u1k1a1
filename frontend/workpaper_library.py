"""Pure helpers for safely grouping workpapers by client."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path


UNASSIGNED_CLIENT = "Unassigned client"

_WORKPAPER_FILENAME = re.compile(
    r"^(?P<prefix>.+?)_workpaper_\d{8}_\d{6}(?:_revision_\d{8}_\d{6})?$",
    flags=re.IGNORECASE,
)
_TEST_PREFIX = re.compile(r"^test\d+[_\-\s]+", flags=re.IGNORECASE)
_INCOME_YEAR = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def infer_client_name_from_workpaper_filename(path: Path) -> str | None:
    """Return a conservative client tag from a standard workpaper filename.

    We only infer from the generator's `client_workpaper_timestamp.xlsx`
    convention.  A generic filename such as `workpaper_timestamp.xlsx` or an
    arbitrary Excel upload stays unassigned.  The function deliberately does
    not use fuzzy matching, so similar names cannot silently merge clients.
    """

    match = _WORKPAPER_FILENAME.fullmatch(path.stem)
    if not match:
        return None

    prefix = _TEST_PREFIX.sub("", match.group("prefix"))
    year_match = _INCOME_YEAR.search(prefix)
    if year_match:
        prefix = prefix[:year_match.start()]

    display_name = re.sub(r"[_\-]+", " ", prefix)
    display_name = re.sub(r"\s+", " ", display_name).strip(" ._-")
    display_name = " ".join(
        word if not word.islower() else word.title()
        for word in display_name.split()
    )
    return display_name or None


def client_tag_for_workpaper(
    path: Path,
    metadata: dict[str, object] | None,
) -> tuple[str | None, str]:
    """Return client name and provenance, favouring saved user metadata."""

    saved_name = str((metadata or {}).get("client_name", "") or "").strip()
    if saved_name:
        return saved_name, "saved_metadata"

    inferred_name = infer_client_name_from_workpaper_filename(path)
    if inferred_name:
        return inferred_name, "filename_inferred"

    return None, "unassigned"


def _client_group_key(client_name: str) -> str:
    """Group case/spacing variants without treating different names as aliases."""

    return re.sub(r"\s+", " ", client_name).strip().casefold()


def client_group_name(
    metadata: dict[str, object] | None,
    workpaper_path: Path | None = None,
) -> str:
    """Return a display-safe client group without exposing a filesystem path."""

    if workpaper_path is not None:
        client_name, _ = client_tag_for_workpaper(workpaper_path, metadata)
    else:
        client_name = str((metadata or {}).get("client_name", "") or "").strip()
    return client_name or UNASSIGNED_CLIENT


def group_workpapers_by_client(
    paths: Iterable[Path],
    *,
    metadata_loader: Callable[[Path], dict[str, object] | None],
) -> dict[str, list[Path]]:
    """Group existing workpapers by saved client name, newest first per group."""

    grouped: dict[str, tuple[str, list[Path]]] = {}
    for path in paths:
        group = client_group_name(metadata_loader(path), path)
        key = _client_group_key(group)
        if key not in grouped:
            grouped[key] = (group, [])
        grouped[key][1].append(path)

    for _, group_paths in grouped.values():
        group_paths.sort(key=lambda path: path.stat().st_mtime, reverse=True)

    return {
        display_name: group_paths
        for display_name, group_paths in sorted(
            grouped.values(),
            key=lambda item: item[0].casefold(),
        )
    }


def build_client_index(
    paths: Iterable[Path],
    *,
    metadata_loader: Callable[[Path], dict[str, object] | None],
) -> list[dict[str, object]]:
    """Build a serialisable audit index with each tag's provenance."""

    grouped = group_workpapers_by_client(paths, metadata_loader=metadata_loader)
    index: list[dict[str, object]] = []
    for client_name, group_paths in grouped.items():
        workpapers = []
        for path in group_paths:
            _, tag_source = client_tag_for_workpaper(path, metadata_loader(path))
            workpapers.append({"path": str(path), "tag_source": tag_source})
        index.append({"client_name": client_name, "workpapers": workpapers})
    return index
