"""Tests for email-digest/cli.py (#167)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml


_SCRIPT = Path(__file__).resolve().parent.parent / "cli.py"
_spec = importlib.util.spec_from_file_location("email_digest_cli", _SCRIPT)
cli = importlib.util.module_from_spec(_spec)
sys.modules["email_digest_cli"] = cli
assert _spec.loader is not None
_spec.loader.exec_module(cli)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from lib import obsidian_md
from lib import project_resolver as pr


# ---------- fixtures ----------

def _write_config(tmp_path: Path, presets: dict) -> Path:
    cfg = tmp_path / "digest-config.yaml"
    cfg.write_text(yaml.safe_dump({"sender": "test@example.com", "presets": presets}))
    return cfg


def _setup_vault(
    monkeypatch, tmp_path: Path, *,
    vault: str = "V",
    projects: list[tuple[str, str]] = (),  # (name, client)
) -> Path:
    vaults_base = tmp_path / "vaults"
    projects_dir = vaults_base / vault / "Projects"
    projects_dir.mkdir(parents=True)
    for name, client in projects:
        obsidian_md.write(projects_dir / f"{name}.md", {
            "project": name, "host": "jns-mac", "client": client,
            "status": "active", "focus": f"focus for {name}",
            "next_steps": [], "blockers": [], "open_questions": [],
            "stack": [], "repo_path": "~/x", "repo_remote": "",
        }, f"# {name}\n")
    subs_file = tmp_path / "subs.json"
    subs_file.write_text(json.dumps({
        vault: {"subscribed": [n for n, _ in projects], "ssh_writes": []},
    }))
    monkeypatch.setattr(pr, "VAULTS_BASE", vaults_base)
    monkeypatch.setattr(pr, "SUBSCRIPTIONS_PATH", subs_file)
    return vaults_base


# ---------- load_config ----------

def test_load_config_basic(tmp_path):
    cfg = _write_config(tmp_path, {
        "p1": {"vault": "V", "client": "personal",
               "recipient": "x@y", "subject_template": "{date}"},
    })
    out = cli.load_config(cfg)
    assert "p1" in out["presets"]
    assert out["presets"]["p1"]["vault"] == "V"


def test_load_config_missing_file_errors(tmp_path):
    with pytest.raises(cli.DigestError, match="config not found"):
        cli.load_config(tmp_path / "missing.yaml")


def test_load_config_missing_required_field_errors(tmp_path):
    cfg = _write_config(tmp_path, {
        "bad": {"vault": "V", "client": "personal"},  # missing recipient + subject_template
    })
    with pytest.raises(cli.DigestError, match="missing required fields"):
        cli.load_config(cfg)


def test_load_config_malformed_yaml(tmp_path):
    cfg = tmp_path / "bad.yaml"
    cfg.write_text("presets:\n  x:\n    - bad: nested wrong\n: : :")
    with pytest.raises(cli.DigestError, match="malformed YAML"):
        cli.load_config(cfg)


def test_load_config_preset_not_a_mapping(tmp_path):
    cfg = tmp_path / "x.yaml"
    cfg.write_text("presets:\n  bad: just a string\n")
    with pytest.raises(cli.DigestError, match="must be a mapping"):
        cli.load_config(cfg)


# ---------- list_presets ----------

def test_list_presets_empty():
    out = cli.list_presets({"presets": {}})
    assert "no presets" in out


def test_list_presets_renders_rows():
    out = cli.list_presets({"presets": {
        "p1": {"vault": "V1", "client": "personal", "recipient": "a@b",
               "description": "desc1"},
        "p2": {"vault": "V2", "client": "vital", "recipient": "c@d",
               "description": "desc2"},
    }})
    assert "p1" in out
    assert "p2" in out
    assert "personal" in out
    assert "vital" in out


# ---------- render_preset_digest ----------

def test_render_preset_digest_basic(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path,
                               projects=[("a", "personal"), ("b", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}", "default_window": "weekly"}
    out = cli.render_preset_digest(preset, vaults_base=vaults_base)
    assert "# V" in out
    assert "weekly" in out
    assert "## a" in out
    assert "## b" in out


def test_render_preset_digest_window_override(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path, projects=[("a", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}", "default_window": "weekly"}
    out = cli.render_preset_digest(preset, vaults_base=vaults_base, window="daily")
    assert "daily" in out


def test_render_preset_digest_annotates_owner_filter(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path, projects=[("a", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}", "default_window": "daily",
              "project": "*", "owner_filter": "Paul"}
    out = cli.render_preset_digest(preset, vaults_base=vaults_base)
    assert "owner filter: Paul" in out


def test_render_preset_digest_refuses_project_scoped_preset(monkeypatch, tmp_path):
    """Codex 2026-05-13 finding #1: a preset with `project: <name>` (not "*")
    must be refused rather than rendering the whole vault — otherwise sibling
    projects in the same vault get silently included even though the
    confirmation line presented a narrower scope.
    """
    vaults_base = _setup_vault(monkeypatch, tmp_path,
                                projects=[("a", "personal"), ("b", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}", "default_window": "daily",
              "project": "a"}
    with pytest.raises(cli.DigestError, match="project-level filtering is not yet"):
        cli.render_preset_digest(preset, vaults_base=vaults_base)


def test_project_scoped_preset_never_leaks_sibling_projects(monkeypatch, tmp_path):
    """End-to-end regression for the leakage scenario Codex flagged: vault has
    same-client projects a + b; a preset that says `project: a` must NOT
    produce any output containing b. The runtime refusal accomplishes this
    by raising before render — assert the raise here.
    """
    vaults_base = _setup_vault(monkeypatch, tmp_path,
                                projects=[("a", "personal"), ("b", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}", "default_window": "daily",
              "project": "a"}
    with pytest.raises(cli.DigestError):
        cli.render_preset_digest(preset, vaults_base=vaults_base)


def test_render_preset_digest_wildcard_project_allowed(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path,
                                projects=[("a", "personal"), ("b", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}", "default_window": "daily",
              "project": "*"}
    out = cli.render_preset_digest(preset, vaults_base=vaults_base)
    assert "## a" in out
    assert "## b" in out


def test_render_preset_digest_no_project_field_treated_as_wildcard(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path, projects=[("a", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}", "default_window": "daily"}
    out = cli.render_preset_digest(preset, vaults_base=vaults_base)
    assert "## a" in out


def test_render_preset_digest_invalid_window_errors(monkeypatch, tmp_path):
    _setup_vault(monkeypatch, tmp_path, projects=[("a", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    with pytest.raises(cli.DigestError, match="invalid window"):
        cli.render_preset_digest(preset, window="quarterly")


# ---------- projects_in_digest ----------

def test_projects_in_digest_extracts_names():
    body = """\
# V — weekly

## agents — active
**Focus**: x

## buddy — paused
**Focus**: y
"""
    assert cli.projects_in_digest(body) == ["agents", "buddy"]


def test_projects_in_digest_dedups():
    body = "## a — x\n## a — y\n## b — z\n"
    assert cli.projects_in_digest(body) == ["a", "b"]


# ---------- §6.5 #1 vault validation ----------

def test_validate_vault_consistency_clean(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path,
                               projects=[("a", "personal"), ("b", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    body = "## a — active\n## b — paused\n"
    cli.validate_vault_consistency(preset, body, vaults_base=vaults_base)  # no raise


def test_validate_vault_consistency_refuses_on_mismatch(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path,
                               projects=[("a", "personal"), ("b", "vital")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    body = "## a — active\n## b — active\n"
    with pytest.raises(cli.DigestError, match="digest scope mismatch"):
        cli.validate_vault_consistency(preset, body, vaults_base=vaults_base)


def test_validate_vault_consistency_lists_offending_projects(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path,
                               projects=[("a", "vital"), ("b", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    body = "## a — active\n## b — active\n"
    with pytest.raises(cli.DigestError) as exc:
        cli.validate_vault_consistency(preset, body, vaults_base=vaults_base)
    assert "a" in str(exc.value)
    assert "vital" in str(exc.value)


def test_validate_skips_projects_with_missing_note(monkeypatch, tmp_path):
    vaults_base = _setup_vault(monkeypatch, tmp_path, projects=[("a", "personal")])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    # Body mentions a project that has no note on disk — should not raise
    body = "## a — active\n## ghost — _(no project note)_\n"
    cli.validate_vault_consistency(preset, body, vaults_base=vaults_base)


# ---------- §6.5 #3 confirmation line ----------

def test_confirmation_line_explicit_context():
    preset = {"vault": "V", "client": "personal",
              "recipient": "ai@x", "project": "p", "owner_filter": "Paul",
              "subject_template": "{date}"}
    line = cli.confirmation_line(preset)
    assert "Sending to ai@x" in line
    assert "vault: V" in line
    assert "project: p" in line
    assert "owner-filter: Paul" in line


def test_confirmation_line_omits_owner_when_unset():
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    line = cli.confirmation_line(preset)
    assert "owner-filter" not in line


# ---------- subject formatting + drafts ----------

def test_format_subject_substitutes_date_and_vault():
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{vault} {date}"}
    assert cli.format_subject(preset, "2026-05-13") == "V 2026-05-13"


def test_write_draft_creates_dir_and_file(tmp_path):
    path = cli.write_draft("paul-jason", "body content\n",
                            drafts_dir=tmp_path / "drafts",
                            today_iso="2026-05-13")
    assert path.exists()
    assert path.read_text() == "body content\n"
    assert path.name == "paul-jason-2026-05-13.md"


def test_archive_sent_creates_dir_and_file(tmp_path):
    path = cli.archive_sent("paul-jason", "sent body\n",
                             sent_dir=tmp_path / "sent",
                             today_iso="2026-05-13")
    assert path.exists()
    assert path.read_text() == "sent body\n"


# ---------- send_via_graph ----------

def test_send_via_graph_invokes_send_mail(tmp_path):
    captured = {}

    def fake_runner(cmd, **kwargs):
        captured["cmd"] = list(cmd)

        class Result:
            returncode = 0
            stdout = "ok\n"
            stderr = ""
        return Result()

    rc, out, err = cli.send_via_graph(
        "x@y", "subj", "body\n",
        send_mail_script=tmp_path / "send_mail.py",
        runner=fake_runner,
    )
    assert rc == 0
    cmd = captured["cmd"]
    assert cmd[0] == "python3"
    assert "--to" in cmd
    assert "x@y" in cmd
    assert "--subject" in cmd
    assert "subj" in cmd
    assert "--content-type" in cmd
    assert "Markdown" in cmd


def test_send_via_graph_cleans_tmp_body_file(tmp_path):
    """The temp body file must not leak after the runner returns."""
    def fake_runner(cmd, **kwargs):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()
    cli.send_via_graph("x@y", "s", "b\n",
                       send_mail_script=tmp_path / "x.py",
                       runner=fake_runner)
    leftovers = list(Path(tempfile.gettempdir()).glob("email-digest-*.md"))
    assert leftovers == []


# ---------- interactive flow ----------

def test_interactive_flow_n_cancels(tmp_path):
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    outcome, path = cli.interactive_flow(
        "p", preset, "body\n",
        drafts_dir=tmp_path / "d", sent_dir=tmp_path / "s",
        today_iso="2026-05-13", auto_choice="n",
    )
    assert outcome == "cancelled"
    assert path is None
    # Draft removed
    assert not (tmp_path / "d" / "p-2026-05-13.md").exists()


def test_interactive_flow_s_saves_draft(tmp_path):
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    outcome, path = cli.interactive_flow(
        "p", preset, "body\n",
        drafts_dir=tmp_path / "d", sent_dir=tmp_path / "s",
        today_iso="2026-05-13", auto_choice="s",
    )
    assert outcome == "saved"
    assert path is not None
    assert path.read_text() == "body\n"


def test_interactive_flow_y_sends(tmp_path):
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "weekly {date}"}

    def fake_runner(cmd, **kwargs):
        class Result:
            returncode = 0
            stdout = ""
            stderr = ""
        return Result()

    outcome, path = cli.interactive_flow(
        "p", preset, "body\n",
        drafts_dir=tmp_path / "d", sent_dir=tmp_path / "s",
        send_mail_script=tmp_path / "fake.py",
        today_iso="2026-05-13", auto_choice="y",
        runner=fake_runner,
    )
    assert outcome == "sent"
    assert path is not None
    assert (tmp_path / "s" / "p-2026-05-13.md").exists()
    # Draft removed after successful send
    assert not (tmp_path / "d" / "p-2026-05-13.md").exists()


def test_interactive_flow_y_send_fails_preserves_draft(tmp_path):
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}

    def fake_runner(cmd, **kwargs):
        class Result:
            returncode = 1
            stdout = ""
            stderr = "auth failed"
        return Result()

    outcome, path = cli.interactive_flow(
        "p", preset, "body\n",
        drafts_dir=tmp_path / "d", sent_dir=tmp_path / "s",
        send_mail_script=tmp_path / "fake.py",
        today_iso="2026-05-13", auto_choice="y",
        runner=fake_runner,
    )
    assert outcome == "send-failed"
    assert path is not None
    assert path.exists()  # draft preserved


def test_interactive_flow_invalid_then_n(tmp_path):
    """prompt_choice should re-prompt on garbage input."""
    inputs = iter(["zzz", "?", "n"])
    preset = {"vault": "V", "client": "personal", "recipient": "x@y",
              "subject_template": "{date}"}
    outcome, _ = cli.interactive_flow(
        "p", preset, "body\n",
        drafts_dir=tmp_path / "d", sent_dir=tmp_path / "s",
        today_iso="2026-05-13",
        input_fn=lambda _: next(inputs),
    )
    assert outcome == "cancelled"


# ---------- list_sent ----------

def test_list_sent_empty(tmp_path):
    assert cli.list_sent(sent_dir=tmp_path) == []


def test_list_sent_filters_by_since(tmp_path):
    sent_dir = tmp_path / "sent"
    sent_dir.mkdir()
    (sent_dir / "p-2026-04-01.md").write_text("a")
    (sent_dir / "p-2026-05-13.md").write_text("b")
    paths = cli.list_sent(since="2026-05-01", sent_dir=sent_dir)
    names = [p.name for p in paths]
    assert "p-2026-05-13.md" in names
    assert "p-2026-04-01.md" not in names


# ---------- main() integration ----------

def test_main_preset_list(monkeypatch, tmp_path, capsys):
    cfg = _write_config(tmp_path, {
        "x": {"vault": "V", "client": "personal", "recipient": "a@b",
              "subject_template": "{date}"}
    })
    rc = cli.main(["preset", "list", "--config", str(cfg)])
    assert rc == 0
    assert "x" in capsys.readouterr().out


def test_main_preset_run_unknown_name(monkeypatch, tmp_path, capsys):
    cfg = _write_config(tmp_path, {
        "x": {"vault": "V", "client": "personal", "recipient": "a@b",
              "subject_template": "{date}"}
    })
    rc = cli.main(["preset", "run", "missing", "--config", str(cfg)])
    assert rc == 1
    assert "unknown preset" in capsys.readouterr().err


def test_main_sent_lists_archive(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "SENT_DIR", tmp_path / "sent")
    (tmp_path / "sent").mkdir()
    (tmp_path / "sent" / "p-2026-05-13.md").write_text("body")
    rc = cli.main(["sent"])
    assert rc == 0
    assert "p-2026-05-13.md" in capsys.readouterr().out


def test_main_no_subcommand_errors():
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2


# Bridge: import tempfile lazily so test_send_via_graph_cleans_tmp_body_file works
import tempfile  # noqa: E402
