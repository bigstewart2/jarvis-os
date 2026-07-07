import { useState } from "react";
import type { NoteMatch } from "../api/client";
import { fetchNoteContent, searchNotes } from "../api/client";

export function NotesWidget() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<NoteMatch[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [expandedPath, setExpandedPath] = useState<string | null>(null);
  const [expandedContent, setExpandedContent] = useState<string | null>(null);

  const handleSearch = async () => {
    setError(null);
    try {
      const results = await searchNotes(query);
      setMatches(results);
      setExpandedPath(null);
      setExpandedContent(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleExpand = async (path: string) => {
    setError(null);
    try {
      const content = await fetchNoteContent(path);
      setExpandedPath(path);
      setExpandedContent(content);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <div className="rounded-lg border border-gray-300 p-4">
      <h2 className="text-lg font-semibold mb-2">Notes</h2>
      <div className="flex gap-2 mb-2">
        <input
          aria-label="Search notes"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="border border-gray-300 rounded px-2 py-1 flex-1"
        />
        <button onClick={handleSearch} className="bg-blue-600 text-white rounded px-3 py-1">
          Search
        </button>
      </div>
      {error && (
        <p data-testid="notes-widget-error" className="text-sm text-red-600 mb-2">
          {error}
        </p>
      )}
      <ul>
        {matches.map((match) => (
          <li key={match.path} className="text-sm mb-1">
            <button onClick={() => handleExpand(match.path)} className="underline">
              {match.title}
            </button>
            <span> — {match.excerpt}</span>
            {expandedPath === match.path && (
              <pre data-testid="note-content" className="mt-1 text-xs bg-gray-100 p-2 rounded whitespace-pre-wrap">
                {expandedContent ?? "Could not load note content."}
              </pre>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}
