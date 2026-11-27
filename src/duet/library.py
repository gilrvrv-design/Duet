"""The duet library (spec §5.9): versions, forks, featured examples and search.

Plain functions over a store, so the rules can be used and tested without the API.
"""

from __future__ import annotations

from pathlib import Path

from duet.difficulty import pianist_difficulty
from duet.score import DuetScore
from duet.storage import Record, Store

KIND = "duet"


def add_duet(store: Store, score: DuetScore, **meta) -> Record:
    """A new duet starts its own line (root) at version 1."""
    record = store.add(KIND, score, **meta)
    return store.update_meta(KIND, record.id, root=record.id, version=1)


def add_version(store: Store, parent_id: str, score: DuetScore, **meta) -> Record:
    """A new version in the same line as ``parent_id`` (variations, repairs)."""
    parent = store.get(KIND, parent_id)
    return store.add(
        KIND,
        score,
        parent=parent_id,
        root=parent.meta.get("root", parent_id),
        version=parent.meta.get("version", 1) + 1,
        **meta,
    )


def versions(store: Store, duet_id: str) -> list[Record]:
    root = store.get(KIND, duet_id).meta.get("root", duet_id)
    line = [r for r in store.list(KIND) if r.meta.get("root") == root]
    return sorted(line, key=lambda r: r.meta.get("version", 1))


def seed_featured(store: Store, examples_dir: Path | None) -> None:
    """Add the example duets once, marked as featured."""
    if examples_dir is None or not Path(examples_dir).is_dir():
        return
    if any(r.meta.get("featured") for r in store.list(KIND)):
        return
    for path in sorted(Path(examples_dir).glob("*.json")):
        score = DuetScore.model_validate_json(path.read_text(encoding="utf-8"))
        add_duet(store, score, source="example", featured=True)


def search(
    store: Store,
    q: str = "",
    difficulty: int | None = None,
    max_bars: int | None = None,
    featured: bool | None = None,
    public: bool | None = None,
    limit: int = 20,
) -> list[Record]:
    """Keyword search: more matching words first, then newest."""
    words = [w for w in q.lower().split() if w]
    hits = []
    for record in store.list(KIND):
        score: DuetScore = record.data
        if difficulty is not None and pianist_difficulty(score) != difficulty:
            continue
        if max_bars is not None and score.bar_count > max_bars:
            continue
        if featured is not None and bool(record.meta.get("featured")) != featured:
            continue
        if public is not None and (record.meta.get("visibility") == "public") != public:
            continue
        text = " ".join(
            [score.meta.title, score.meta.prompt or "", score.meta.key, *score.meta.style_tags]
        ).lower()
        matched = sum(w in text for w in words)
        if words and not matched:
            continue
        hits.append((matched, record.created_at, record))
    hits.sort(key=lambda h: (-h[0], -h[1]))
    return [r for _, _, r in hits[:limit]]
