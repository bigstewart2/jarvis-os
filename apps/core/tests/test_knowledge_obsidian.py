import shutil
from pathlib import Path

from core.providers.knowledge.obsidian import ObsidianVaultSource

FIXTURE_VAULT = Path(__file__).resolve().parent / "fixtures" / "vault"


def test_finds_match_with_correct_fields():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    matches = source.search("jarvis")

    assert len(matches) == 1
    assert matches[0]["path"] == "project-ideas.md"
    assert matches[0]["title"] == "Project Ideas"
    assert "jarvis" in matches[0]["excerpt"].lower()
    assert matches[0]["line_number"] == 5


def test_case_insensitive_matching():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    matches = source.search("RECIPE")

    assert len(matches) == 1
    assert matches[0]["path"] == "no-heading.md"
    assert matches[0]["title"] == "no-heading"


def test_respects_limit():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    matches = source.search("note", limit=2)

    assert len(matches) == 2


def test_no_matches_returns_empty_list():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    matches = source.search("zzzznomatchzzzz")

    assert matches == []


def test_missing_vault_directory_returns_empty_list(tmp_path):
    source = ObsidianVaultSource(tmp_path / "does-not-exist")

    matches = source.search("anything")

    assert matches == []


def test_skips_unreadable_file_without_failing_search(tmp_path):
    vault_copy = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault_copy)
    (vault_copy / "broken.md").write_bytes(b"\xff\xfe\x00\x01invalid utf-8 note bytes")

    source = ObsidianVaultSource(vault_copy)

    matches = source.search("note")

    assert all(m["path"] != "broken.md" for m in matches)
    assert len(matches) >= 1


def test_does_not_escape_vault_root(tmp_path):
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    secret_file = outside_dir / "secret.md"
    secret_file.write_text("# Secret\n\nThis contains the word targetphrase.\n")

    vault_copy = tmp_path / "vault"
    shutil.copytree(FIXTURE_VAULT, vault_copy)
    (vault_copy / "escape-link.md").symlink_to(secret_file)

    source = ObsidianVaultSource(vault_copy)

    matches = source.search("targetphrase")

    assert matches == []


def test_read_returns_content_for_existing_note():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read("project-ideas.md")

    assert content is not None
    assert "Jarvis OS should eventually search my notes." in content


def test_read_returns_content_for_nested_note():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read("subdir/nested-note.md")

    assert content is not None
    assert "Quarterly Review" in content


def test_read_returns_none_for_missing_note():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read("does-not-exist.md")

    assert content is None


def test_read_returns_none_for_relative_path_traversal_attempt():
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read("../../../../etc/passwd")

    assert content is None


def test_read_returns_none_for_absolute_path_outside_vault(tmp_path):
    outside_file = tmp_path / "secret.md"
    outside_file.write_text("top secret content")
    source = ObsidianVaultSource(FIXTURE_VAULT)

    content = source.read(str(outside_file))

    assert content is None
