"""Persistent knowledge/memory layer (pustaka/69).

Stores learned outcomes, patterns, and decisions from the self-evolution agent:
- Episodic memory: records of specific events and outcomes
- Semantic memory: generalized knowledge and patterns
- Procedural memory: learned strategies and procedures
- Working memory: current context and active hypotheses
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any


class MemoryType(Enum):
    """Types of persistent memory."""

    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"
    WORKING = "working"


@dataclass
class MemoryEntry:
    """A single memory entry."""

    entry_id: str
    memory_type: MemoryType
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    access_count: int = 0
    relevance_score: float = 1.0
    tags: list[str] = field(default_factory=list)


class PersistentMemory:
    """Persistent knowledge/memory layer.

    Stores memories in JSON format for durability.
    In production, this would use a proper database (SQLite/PostgreSQL).
    """

    def __init__(self, storage_path: Path | str | None = None) -> None:
        self._storage_path = Path(storage_path) if storage_path else None
        self._entries: dict[str, MemoryEntry] = {}
        self._counter = 0
        self._type_index: dict[MemoryType, list[str]] = {
            MemoryType.EPISODIC: [],
            MemoryType.SEMANTIC: [],
            MemoryType.PROCEDURAL: [],
            MemoryType.WORKING: [],
        }
        self._tag_index: dict[str, list[str]] = {}

        if self._storage_path and self._storage_path.exists():
            self.load()

    def store(
        self,
        memory_type: MemoryType,
        content: str,
        metadata: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        relevance_score: float = 1.0,
    ) -> MemoryEntry:
        """Store a new memory entry.

        Args:
            memory_type: Type of memory.
            content: Memory content text.
            metadata: Additional metadata.
            tags: Tags for retrieval.
            relevance_score: Initial relevance score.

        Returns:
            The stored MemoryEntry.
        """
        self._counter += 1
        entry_id = f"mem_{self._counter:06d}"

        entry = MemoryEntry(
            entry_id=entry_id,
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
            tags=tags or [],
            relevance_score=relevance_score,
        )

        self._entries[entry_id] = entry
        self._type_index[memory_type].append(entry_id)

        for tag in entry.tags:
            if tag not in self._tag_index:
                self._tag_index[tag] = []
            self._tag_index[tag].append(entry_id)

        if self._storage_path:
            self.save()

        return entry

    def retrieve(self, entry_id: str) -> MemoryEntry | None:
        """Retrieve a specific memory by ID.

        Args:
            entry_id: Memory entry ID.

        Returns:
            MemoryEntry, or None if not found.
        """
        entry = self._entries.get(entry_id)
        if entry:
            entry.access_count += 1
            entry.updated_at = datetime.now(UTC).isoformat()
        return entry

    def search(
        self,
        memory_type: MemoryType | None = None,
        tags: list[str] | None = None,
        query: str | None = None,
        limit: int = 10,
    ) -> list[MemoryEntry]:
        """Search memories by type, tags, or content.

        Args:
            memory_type: Filter by memory type.
            tags: Filter by tags (any match).
            query: Text search in content.
            limit: Maximum results.

        Returns:
            List of matching MemoryEntry objects.
        """
        candidates: list[str] = []

        if memory_type:
            candidates = self._type_index.get(memory_type, []).copy()
        else:
            candidates = list(self._entries.keys())

        if tags:
            tag_matches: set[str] = set()
            for tag in tags:
                tag_matches.update(self._tag_index.get(tag, []))
            candidates = [c for c in candidates if c in tag_matches]

        results: list[MemoryEntry] = []
        for eid in candidates:
            entry = self._entries.get(eid)
            if entry is None:
                continue
            if query and query.lower() not in entry.content.lower():
                continue
            results.append(entry)

        # Sort by relevance score, then by recency
        results.sort(key=lambda e: (e.relevance_score, e.updated_at), reverse=True)

        return results[:limit]

    def update(
        self,
        entry_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
        relevance_score: float | None = None,
        tags: list[str] | None = None,
    ) -> MemoryEntry | None:
        """Update an existing memory entry.

        Args:
            entry_id: Entry to update.
            content: New content.
            metadata: New metadata (merged).
            relevance_score: New relevance score.
            tags: New tags (replaced).

        Returns:
            Updated MemoryEntry, or None if not found.
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            return None

        if content is not None:
            entry.content = content
        if metadata is not None:
            entry.metadata.update(metadata)
        if relevance_score is not None:
            entry.relevance_score = relevance_score
        if tags is not None:
            # Remove old tags from index
            for old_tag in entry.tags:
                if old_tag in self._tag_index and entry_id in self._tag_index[old_tag]:
                    self._tag_index[old_tag].remove(entry_id)
            entry.tags = tags
            for tag in tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                self._tag_index[tag].append(entry_id)

        entry.updated_at = datetime.now(UTC).isoformat()

        if self._storage_path:
            self.save()

        return entry

    def forget(self, entry_id: str) -> bool:
        """Remove a memory entry (forgetting).

        Args:
            entry_id: Entry to forget.

        Returns:
            True if removed, False if not found.
        """
        entry = self._entries.get(entry_id)
        if entry is None:
            return False

        # Remove from type index
        if entry_id in self._type_index.get(entry.memory_type, []):
            self._type_index[entry.memory_type].remove(entry_id)

        # Remove from tag index
        for tag in entry.tags:
            if tag in self._tag_index and entry_id in self._tag_index[tag]:
                self._tag_index[tag].remove(entry_id)

        del self._entries[entry_id]

        if self._storage_path:
            self.save()

        return True

    def consolidate(self, threshold: float = 0.1) -> int:
        """Consolidate memories by removing low-relevance entries.

        Args:
            threshold: Relevance score below which entries are forgotten.

        Returns:
            Number of entries removed.
        """
        to_remove = [
            eid for eid, entry in self._entries.items()
            if entry.relevance_score < threshold
        ]
        for eid in to_remove:
            self.forget(eid)
        return len(to_remove)

    def save(self) -> None:
        """Save memories to disk."""
        if not self._storage_path:
            return

        data = {
            "entries": {
                eid: {
                    **asdict(e),
                    "memory_type": e.memory_type.value,
                }
                for eid, e in self._entries.items()
            },
            "counter": self._counter,
        }

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(json.dumps(data, indent=2, default=str))

    def load(self) -> None:
        """Load memories from disk."""
        if not self._storage_path or not self._storage_path.exists():
            return

        data = json.loads(self._storage_path.read_text())
        self._counter = data.get("counter", 0)

        for eid, entry_data in data.get("entries", {}).items():
            entry_data["memory_type"] = MemoryType(entry_data["memory_type"])
            entry = MemoryEntry(**entry_data)
            self._entries[eid] = entry
            self._type_index[entry.memory_type].append(eid)
            for tag in entry.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = []
                self._tag_index[tag].append(eid)

    @property
    def count(self) -> int:
        """Total number of stored memories."""
        return len(self._entries)

    def stats(self) -> dict[str, int]:
        """Get memory statistics by type."""
        return {
            mt.value: len(ids) for mt, ids in self._type_index.items()
        }
