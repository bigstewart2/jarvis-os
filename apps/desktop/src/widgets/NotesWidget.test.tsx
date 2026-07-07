import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { NotesWidget } from "./NotesWidget";
import * as client from "../api/client";

describe("NotesWidget", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    cleanup();
  });

  it("searches for notes and renders matches", async () => {
    vi.spyOn(client, "searchNotes").mockResolvedValue([
      { path: "project-ideas.md", title: "Project Ideas", excerpt: "Jarvis OS should eventually search my notes.", line_number: 5 },
    ]);

    render(<NotesWidget />);
    fireEvent.change(screen.getByLabelText("Search notes"), { target: { value: "jarvis" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(screen.getByText("Project Ideas")).toBeInTheDocument();
    });
    expect(client.searchNotes).toHaveBeenCalledWith("jarvis");
  });

  it("expands a match to show full note content on click", async () => {
    vi.spyOn(client, "searchNotes").mockResolvedValue([
      { path: "project-ideas.md", title: "Project Ideas", excerpt: "excerpt text", line_number: 5 },
    ]);
    vi.spyOn(client, "fetchNoteContent").mockResolvedValue("# Project Ideas\n\nFull content here.");

    render(<NotesWidget />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      expect(screen.getByText("Project Ideas")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Project Ideas" }));

    await waitFor(() => {
      expect(screen.getByTestId("note-content")).toHaveTextContent("Full content here.");
    });
    expect(client.fetchNoteContent).toHaveBeenCalledWith("project-ideas.md");
  });

  it("shows an error message when search fails", async () => {
    vi.spyOn(client, "searchNotes").mockRejectedValue(new Error("boom"));

    render(<NotesWidget />);
    fireEvent.click(screen.getByRole("button", { name: "Search" }));

    await waitFor(() => {
      expect(screen.getByTestId("notes-widget-error")).toHaveTextContent("boom");
    });
  });
});
