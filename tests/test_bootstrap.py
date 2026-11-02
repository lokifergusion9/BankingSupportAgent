from bankingsupportagent import bootstrap


def test_fresh_machine_gets_everything_then_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "JWT_PRIVATE_KEY_PATH", tmp_path / "keys" / "private.pem")
    monkeypatch.setattr(bootstrap, "JWT_PUBLIC_KEY_PATH", tmp_path / "keys" / "public.pem")
    monkeypatch.setattr(bootstrap, "DB_PATH", tmp_path / "bank.db")
    monkeypatch.setattr(bootstrap, "CHROMA_DIR", tmp_path / "chroma")
    monkeypatch.setattr("bankingsupportagent.keys.KEYS_DIR", tmp_path / "keys")

    def fake_seed():
        (tmp_path / "bank.db").write_text("db")

    def fake_index():
        (tmp_path / "chroma").mkdir()
        (tmp_path / "chroma" / "index").write_text("x")

    monkeypatch.setattr("bankingsupportagent.db.seed.seed", fake_seed)
    monkeypatch.setattr("bankingsupportagent.rag.ingest.build_vector_store", fake_index)
    # generate_keys() takes its folder as a default argument, so point it at the temp folder explicitly
    from bankingsupportagent import keys
    real_generate = keys.generate_keys
    monkeypatch.setattr(keys, "generate_keys", lambda: real_generate(tmp_path / "keys"))

    assert bootstrap.ensure_ready() == ["login keys", "demo database", "policy index"]
    assert (tmp_path / "keys" / "private.pem").exists()
    assert (tmp_path / "keys" / "public.pem").exists()

    assert bootstrap.ensure_ready() == []       # second start changes nothing


def test_existing_files_are_never_overwritten(tmp_path, monkeypatch):
    (tmp_path / "keys").mkdir()
    for name in ("private.pem", "public.pem"):
        (tmp_path / "keys" / name).write_text("mine")
    (tmp_path / "bank.db").write_text("mine")
    (tmp_path / "chroma").mkdir()
    (tmp_path / "chroma" / "index").write_text("mine")
    monkeypatch.setattr(bootstrap, "JWT_PRIVATE_KEY_PATH", tmp_path / "keys" / "private.pem")
    monkeypatch.setattr(bootstrap, "JWT_PUBLIC_KEY_PATH", tmp_path / "keys" / "public.pem")
    monkeypatch.setattr(bootstrap, "DB_PATH", tmp_path / "bank.db")
    monkeypatch.setattr(bootstrap, "CHROMA_DIR", tmp_path / "chroma")

    assert bootstrap.ensure_ready() == []
    assert (tmp_path / "bank.db").read_text() == "mine"
