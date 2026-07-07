from pathlib import Path

from core.providers.knowledge.base import NoteMatch


def _build_excerpt(line: str, query_lower: str, max_len: int = 200) -> str:
    stripped = line.strip()
    if len(stripped) <= max_len:
        return stripped

    idx = stripped.lower().find(query_lower)
    if idx == -1:
        return stripped[:max_len]

    start = max(0, idx - max_len // 2)
    end = min(len(stripped), start + max_len)
    excerpt = stripped[start:end]
    if start > 0:
        excerpt = "…" + excerpt
    if end < len(stripped):
        excerpt = excerpt + "…"
    return excerpt


class ObsidianVaultSource:
    def __init__(self, vault_root: Path):
        self.vault_root = vault_root

    def search(self, query: str, limit: int = 10) -> list[NoteMatch]:
        if not self.vault_root.exists():
            return []

        resolved_root = self.vault_root.resolve()
        query_lower = query.lower()
        matches: list[NoteMatch] = []

        for path in sorted(self.vault_root.rglob("*.md")):
            resolved_path = path.resolve()
            if not resolved_path.is_relative_to(resolved_root):
                continue

            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue

            lines = text.splitlines()
            match_line_index = None
            for index, line in enumerate(lines):
                if query_lower in line.lower():
                    match_line_index = index
                    break
            if match_line_index is None:
                continue

            title = path.stem
            for line in lines:
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            matches.append({
                "path": str(path.relative_to(self.vault_root)),
                "title": title,
                "excerpt": _build_excerpt(lines[match_line_index], query_lower),
                "line_number": match_line_index + 1,
            })
            if len(matches) >= limit:
                break

        return matches
