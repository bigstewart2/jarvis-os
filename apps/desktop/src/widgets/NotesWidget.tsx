import { useState } from "react";
import type { NoteMatch } from "../api/client";
import { fetchNoteContent, searchNotes } from "../api/client";
import { Card, EmptyHint } from "../components/Card";

export function NotesWidget() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<NoteMatch[]>([]);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedPath, setExpandedPath] = useState<string | null>(null);
  const [expandedContent, setExpandedContent] = useState<string | null>(null);

  const handleSearch = async () => {
    setError(null);
    try {
      const results = await searchNotes(query);
      setMatches(results);
      setSearched(true);
      setExpandedPath(null);
      setExpandedContent(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleExpand = async (path: string) => {
    setError(null);
    if (expandedPath === path) {
      setExpandedPath(null);
      setExpandedContent(null);
      return;
    }
    try {
      const content = await fetchNoteContent(path);
      setExpandedPath(path);
      setExpandedContent(content);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Card title="Notes">
      <form
        className="mb-2 flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          void handleSearch();
        }}
      >
        <input
          aria-label="Search notes"
          placeholder="Search your Obsidian vault…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="flex-1 rounded-md border border-edge bg-surface-2 px-2 py-1.5 text-sm placeholder:text-ink-faint"
        />
        <button
          type="submit"
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-ink transition-colors duration-150 hover:opacity-90"
        >
          Search
        </button>
      </form>
      {error && (
        <p data-testid="notes-widget-error" className="mb-2 text-sm text-danger">
          {error}
        </p>
      )}
      {searched && matches.length === 0 && !error && (
        <EmptyHint>No notes matched "{query}".</EmptyHint>
      )}
      <ul className="space-y-1.5">
        {matches.map((match) => (
          <li key={match.path} className="text-sm">
            <button
              onClick={() => handleExpand(match.path)}
              className="font-medium text-primary transition-colors duration-150 hover:underline"
            >
              {match.title}
            </button>
            <span className="text-ink-mute"> — {match.excerpt}</span>
            {expandedPath === match.path && (
              <pre
                data-testid="note-content"
                className="mt-1.5 max-h-72 overflow-y-auto whitespace-pre-wrap rounded-md bg-surface-2 p-3 font-sans text-sm leading-relaxed"
              >
                {expandedContent ?? "Could not load note content."}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
