import shutil

from core.providers.knowledge.obsidian import ObsidianVaultSource

FIXTURE_VAULT = None  # set below after Path import to keep this block copy-pasteable


from pathlib import Path  # noqa: E402

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
