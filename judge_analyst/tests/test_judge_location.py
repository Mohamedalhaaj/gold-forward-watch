"""The analyst judge lives in gold-forward-watch and reads gold-analyst as data (register R-AN-1, R-AN-66, R-AN-69,
R-AN-70; prereg R1(a), §8; review blocker B3).

- Its manifest covers judge_analyst/** and .github/workflows/analyst-judge.yml of THIS repository.
- The gold-analyst clone is named with --repo and read through git objects only; nothing is written into it and no
  analyst module is ever imported (blind: the judge's code imports the standard library and jlib only).
- Its outputs default to reports/judge_analyst/ of this repository, plus the verdict feed
  reports/forward_site/judge_analyst/analyst_verdict.json (byte-identical copy); the system store is this checkout.
"""
import ast
import os
import subprocess
import sys

import pytest

import run_judge

JUDGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(JUDGE)
GITENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
          "GIT_COMMITTER_EMAIL": "t@example.invalid", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}


def test_the_judge_root_is_this_repository():
    assert run_judge.JUDGE_ROOT == ROOT
    assert os.path.exists(os.path.join(ROOT, "judge", "run.py"))               # gold-forward-watch: judge v1 beside it
    files = run_judge.judge_files(ROOT)
    assert ".github/workflows/analyst-judge.yml" in files
    assert "judge_analyst/run_judge.py" in files and "judge_analyst/tests/test_judge_location.py" in files
    assert all(p.startswith("judge_analyst/") or p == ".github/workflows/analyst-judge.yml" for p in files)


def test_the_manifest_is_current():
    """A0 judge_manifest stays quiet only if FROZEN_JUDGE_ANALYST.sha256 lists every judge file at its sha256."""
    ok, sha8 = run_judge.manifest_status(ROOT)
    assert ok, "run: python -I judge_analyst/run_judge.py --write-manifest"
    assert len(sha8) == 8


def test_defaults_point_at_this_repository():
    a = run_judge.resolve(run_judge.parse_args(["--repo", "../ga"]))
    assert a.out == os.path.join(ROOT, "reports", "judge_analyst")
    assert a.site == os.path.join(ROOT, "reports", "forward_site", "judge_analyst")
    assert a.store == ROOT
    assert a.repo == os.path.abspath("../ga")
    off = run_judge.resolve(run_judge.parse_args(["--repo", "x", "--store", "none", "--site", "none"]))
    assert off.store is None and off.site is None


def test_a_run_needs_the_analyst_clone_and_never_defaults_to_this_repository(capsys):
    with pytest.raises(SystemExit):
        run_judge.main(["--api", "none", "--hours", "none"])
    assert "--repo" in capsys.readouterr().err


def _git(repo, *a):
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, env=dict(os.environ, **GITENV))
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_a_run_writes_its_folders_and_leaves_the_analyst_clone_untouched(tmp_path, capsys):
    ga = tmp_path / "ga"
    ga.mkdir()
    _git(ga, "init", "-q", "-b", "main")
    (ga / "analyst").mkdir()
    (ga / "analyst/MODE.json").write_text('{"canary_from": null, "canary_to": null, "live_from": null, '
                                          '"mode": "off", "note": "t", "set_utc": "2026-10-23T00:00:00Z"}\n')
    (ga / "analyst/ga").mkdir()
    (ga / "analyst/ga/__init__.py").write_text("raise SystemExit('the judge imported analyst code')\n")
    _git(ga, "add", ".")
    _git(ga, "commit", "-q", "-m", "seed")
    head = _git(ga, "rev-parse", "HEAD").strip()
    out, site = tmp_path / "gfw/reports/judge_analyst", tmp_path / "gfw/reports/forward_site/judge_analyst"
    rc = run_judge.main(["--repo", str(ga), "--out", str(out), "--site", str(site), "--store", "none",
                         "--api", "none", "--hours", "none", "--now", "2026-11-02T00:00:00Z"])
    assert rc == 0
    assert "analyst_verdict=WARNING" in capsys.readouterr().out                 # A0: no API, no store: never SOUND
    v = (out / "analyst_verdict.json").read_bytes()
    assert (site / "analyst_verdict.json").read_bytes() == v
    assert b'"head_sha": "' + head.encode() + b'"' in v and b'"schema": "analyst-verdict/1"' in v
    assert sorted(os.listdir(site)) == ["analyst_verdict.json"]
    for name in ("ADJUDICATIONS.csv", "FINDINGS.csv", "VERDICTS.csv", "REPORT.md", "evidence.csv"):
        assert (out / name).exists(), name
    assert _git(ga, "status", "--porcelain", "--untracked-files=all") == ""
    assert _git(ga, "rev-parse", "HEAD").strip() == head
    assert not any(m == "ga" or m.startswith("ga.") for m in sys.modules)


def _imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name.split(".")[0], 0
        elif isinstance(node, ast.ImportFrom):
            yield (node.module or "").split(".")[0], node.level


def test_blind_the_judge_imports_only_the_standard_library_and_jlib():
    srcs = [os.path.join(JUDGE, "run_judge.py")] + [os.path.join(JUDGE, "jlib", f)
                                                     for f in sorted(os.listdir(os.path.join(JUDGE, "jlib")))
                                                     if f.endswith(".py")]
    for p in srcs:
        for mod, level in _imports(p):
            assert level > 0 or mod == "jlib" or mod in sys.stdlib_module_names or mod == "__future__", (p, mod)
        text = open(p, encoding="utf-8").read()
        assert "analyst/ga" not in text and "run_window" not in text, p
        assert "sys.path" not in text or p.endswith("run_judge.py"), p
    rj = open(os.path.join(JUDGE, "run_judge.py"), encoding="utf-8").read()
    assert rj.count("sys.path.insert") == 1 and "sys.path.insert(0, HERE)" in rj
