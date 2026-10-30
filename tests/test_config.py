from config import load_config, local_path


def test_local_overrides_main_and_defaults(tmp_path):
    main = tmp_path / "config.yaml"
    main.write_text("sound:\n  volume: 0.5\n  appear: a.wav\ncamera:\n  index: 1\n", encoding="utf-8")
    local_path(main).write_text("sound:\n  volume: 0.9\n", encoding="utf-8")
    cfg = load_config(main)
    assert cfg["sound"]["volume"] == 0.9       # config.local.yaml
    assert cfg["sound"]["appear"] == "a.wav"   # config.yaml
    assert cfg["camera"]["index"] == 1
    assert cfg["camera"]["fps"] == 30          # valor por defecto


def test_works_without_local(tmp_path):
    main = tmp_path / "config.yaml"
    main.write_text("camera:\n  index: 2\n", encoding="utf-8")
    assert load_config(main)["camera"]["index"] == 2
