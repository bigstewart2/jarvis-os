from typing import Protocol, TypedDict, runtime_checkable


class NoteMatch(TypedDict):
    path: str
    title: str
    excerpt: str
    line_number: int


@runtime_checkable
class KnowledgeSource(Protocol):
    def search(self, query: str, limit: int = 10) -> list[NoteMatch]: ...
    def read(self, path: str) -> str | None: ...
