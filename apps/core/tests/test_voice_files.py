import os
import time

from core.voice.files import clear_voice_dir, prune_tts_files, tts_path, upload_path


def test_upload_path_creates_uploads_dir_and_unique_names(tmp_path):
    voice_dir = tmp_path / "voice"

    path1 = upload_path(voice_dir)
    path2 = upload_path(voice_dir)

    assert path1.parent == voice_dir / "uploads"
    assert path1.parent.exists()
    assert path1 != path2
    assert path1.suffix == ".webm"


def test_tts_path_creates_tts_dir_with_wav_extension(tmp_path):
    voice_dir = tmp_path / "voice"

    path = tts_path(voice_dir)

    assert path.parent == voice_dir / "tts"
    assert path.suffix == ".wav"


def test_prune_tts_files_keeps_newest_n_regardless_of_age(tmp_path):
    voice_dir = tmp_path / "voice"
    tts_dir = voice_dir / "tts"
    tts_dir.mkdir(parents=True)
    for i in range(5):
        (tts_dir / f"{i}.wav").write_text("x")

    prune_tts_files(voice_dir, max_age_seconds=0, keep_newest=3)

    remaining = list(tts_dir.iterdir())
    assert len(remaining) == 3


def test_prune_tts_files_deletes_old_files_beyond_keep_newest(tmp_path):
    voice_dir = tmp_path / "voice"
    tts_dir = voice_dir / "tts"
    tts_dir.mkdir(parents=True)
    old_file = tts_dir / "old.wav"
    old_file.write_text("x")
    old_time = time.time() - 7200
    os.utime(old_file, (old_time, old_time))

    prune_tts_files(voice_dir, max_age_seconds=3600, keep_newest=0)

    assert not old_file.exists()


def test_prune_tts_files_keeps_recent_files_even_beyond_keep_newest(tmp_path):
    voice_dir = tmp_path / "voice"
    tts_dir = voice_dir / "tts"
    tts_dir.mkdir(parents=True)
    recent_file = tts_dir / "recent.wav"
    recent_file.write_text("x")

    prune_tts_files(voice_dir, max_age_seconds=3600, keep_newest=0)

    assert recent_file.exists()


def test_clear_voice_dir_removes_all_contents(tmp_path):
    voice_dir = tmp_path / "voice"
    (voice_dir / "uploads").mkdir(parents=True)
    (voice_dir / "uploads" / "stale.webm").write_text("x")

    clear_voice_dir(voice_dir)

    assert voice_dir.exists()
    assert list(voice_dir.iterdir()) == []
