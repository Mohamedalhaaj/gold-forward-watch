"""Isolation (§2.5, §4): lab v2 writes only its own folders; a forced v2 crash leaves v1's run, publish and commit
outputs byte-identical; the workflow runs v2 after v1's commit with continue-on-error and its own commit; the v1
publisher's lab2 keys come from the last summary.json and are left out when it is missing or invalid."""
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

import publish
import run as v1run
import run_v2
import v2_page

ROOT = run_v2.ROOT
V2_DIRS = ("data/system/lab_v2", "reports/system/lab_v2", "reports/forward_site/system/lab_v2")
TIMES = run_v2.SYNTH_TIMES[:6]                      # through 2026-11-21 (v2 runs 11-03, 11-07, 11-14, 11-21)


def snapshot(base, include_v2=False):
    out = {}
    for p in sorted(Path(base).rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(base).as_posix()
        if not include_v2 and rel.startswith(V2_DIRS):
            continue
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def without_lab2(path):
    lines = [ln for ln in Path(path).read_text().splitlines() if not ln.startswith("lab2_")]
    return lines[:-1] + [f"end,{len(lines) - 1}"]


@pytest.fixture(scope="module")
def worlds(tmp_path_factory):
    base = tmp_path_factory.mktemp("iso")
    P0 = run_v2.Paths(base / "raw")
    run_v2.setup_synthetic(P0)
    out = {}
    for name, kw in (("A_v1_only", {"v2": False}), ("B_v2_always_crashes", {"crash_at": "all"}),
                     ("C_v2_crashes_last", {"crash_at": [TIMES[-1]]})):
        shutil.copytree(P0.base, base / name)
        P = run_v2.Paths(base / name)
        out[name] = (P, run_v2.synthetic_runs(P, times=TIMES, log=lambda *a: None, **kw))
    return out


def test_v1_outputs_are_byte_identical_when_v2_always_crashes(worlds):
    PA, _ = worlds["A_v1_only"]
    PB, codes = worlds["B_v2_always_crashes"]
    assert [c for _, c in codes] == [run_v2.EXIT_HALT] * 4
    a, b = snapshot(PA.base), snapshot(PB.base)
    assert a == b                                          # VolMapSystem.csv included: no summary, no lab2 keys
    assert "lab2_state" not in (PB.base / "reports/forward_site/system/VolMapSystem.csv").read_text()
    assert (PB.rep / "HALT.md").exists() and "forced crash" in (PB.rep / "HALT.md").read_text()
    assert len(pd.read_csv(PB.rep / "halts.csv")) == 4 and not (PB.rep / "summary.json").exists()


def test_v1_outputs_are_byte_identical_when_v2_crashes_after_good_runs(worlds):
    PA, _ = worlds["A_v1_only"]
    PC, codes = worlds["C_v2_crashes_last"]
    assert [c for _, c in codes] == [0, 0, 0, run_v2.EXIT_HALT]
    a, c = snapshot(PA.base), snapshot(PC.base)
    vm = "reports/forward_site/system/VolMapSystem.csv"
    assert set(a) == set(c) and {k for k in a if a[k] != c[k]} == {vm}
    assert without_lab2(PA.base / vm) == without_lab2(PC.base / vm)
    kv = publish.parse_system_csv((PC.base / vm).read_text())
    assert kv["lab2_state"] == "RUNNING"                   # published by v1 before the crash, from the 11-14 summary
    s = json.loads((PC.rep / "summary.json").read_text())
    assert s["state"] == "PAUSED" and s["halted"] and "forced crash" in s["halt_reasons"][0]
    # the next v1 run publishes the PAUSED state, and nothing else changes in v1's outputs
    P1 = v1run.Paths(PC.base)
    t = pd.Timestamp("2026-11-28 03:20", tz="UTC")
    info, _ = v1run.one_run(P1, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=lambda *a: None)
    kv = publish.parse_system_csv((PC.base / vm).read_text())
    assert kv["lab2_state"] == "PAUSED" and kv["lab2_days"] == str(s["days"])


def test_v2_writes_only_its_own_folders(worlds, tmp_path):
    PC, _ = worlds["C_v2_crashes_last"]
    P = run_v2.Paths(tmp_path / "w")
    shutil.copytree(PC.base, P.base)
    before, before_all = snapshot(P.base), snapshot(P.base, include_v2=True)
    t = pd.Timestamp("2026-11-28 03:20", tz="UTC")
    code, info = run_v2.guarded_run(P, t, "synthetic", "dry", "dry-placeholder", fetch_on=False, log=lambda *a: None)
    assert code == 0 and info["settled_now"]
    after_all = snapshot(P.base, include_v2=True)
    assert snapshot(P.base) == before
    changed = {k for k in set(after_all) | set(before_all) if after_all.get(k) != before_all.get(k)}
    assert changed and all(k.startswith(V2_DIRS) for k in changed)
    assert "reports/system/lab_v2/HALT.md" in changed and not (P.rep / "HALT.md").exists()   # removed by a good run


# ---------------------------------------------------------------- the workflow (OPS edit)
def steps(text):
    return [m.group(1) for m in re.finditer(r"^      - name: (.+)$", text, flags=re.M)]


def block(text, name):
    i = text.index(f"      - name: {name}\n")
    j = text.find("\n      - name: ", i + 1)
    return text[i: j if j > 0 else len(text)]


def test_the_workflow_runs_v2_after_v1s_commit_with_continue_on_error():
    text = (ROOT / ".github/workflows/system.yml").read_text()
    assert steps(text) == ["System run", "The watch paths are untouched", "Commit the system ledgers", "Lab v2 run",
                           "Lab v2 did not finish", "Commit the lab v2 ledgers",
                           "Fail the job if the run halted or failed"]
    run2 = block(text, "Lab v2 run")
    assert "continue-on-error: true" in run2 and "timeout-minutes: 10" in run2 and "\n        if:" not in run2
    assert "uv run --frozen python -I analysis/system/lab_v2/run_v2.py" in run2
    assert 'export LAB2_EXIT_FILE="$RUNNER_TEMP/lab2_exit"' in run2 and 'echo "finished=1"' in run2
    crash = block(text, "Lab v2 did not finish")
    assert ("if: ${{ !cancelled() && steps.lab2.outcome != 'skipped' && steps.lab2.outputs.finished != '1' }}"
            in crash and "continue-on-error: true" in crash)
    assert "git checkout -q HEAD -- \"$p\"" in crash and "git clean -fdq -- \"$p\"" in crash
    assert "analysis/system/lab_v2/v2_crash.py --reason" in crash
    com2 = block(text, "Commit the lab v2 ledgers")
    assert "continue-on-error: true" in com2 and "if: ${{ !cancelled() && steps.lab2.outcome != 'skipped' }}" in com2
    assert "git add -A" not in text and "git add -- \"$p\"" in com2
    for d in V2_DIRS:
        assert d in com2 and d in crash
    assert block(text, "Fail the job if the run halted or failed").strip().endswith(
        "if: ${{ steps.run.outcome == 'failure' }}\n        run: exit 1".strip())


def step_script(name):
    """The `run: |` body of a step of system.yml, unindented."""
    b = block((ROOT / ".github/workflows/system.yml").read_text(), name)
    body = b[b.index("        run: |\n") + len("        run: |\n"):]
    return "".join(ln[10:] if ln.startswith("          ") else ln.lstrip() for ln in body.splitlines(True))


def fake_bin(d, name, script):
    p = d / name
    p.write_text("#!/bin/bash\n" + script)
    p.chmod(0o755)


@pytest.mark.parametrize("behaviour,code,finished", [
    ("ok", 0, True), ("halt", 1, True), ("ops", 2, True),
    ("killed", 137, False), ("crash_before_main", 1, False), ("uv_failed", 2, False)])
def test_the_step_is_finished_only_when_run_v2_reports_its_own_end(tmp_path, behaviour, code, finished):
    """§2.5 item 2 (lab review MF2): the "Lab v2 run" step sets finished=1 only when run_v2.py wrote the step's own
    exit code to $LAB2_EXIT_FILE; a kill, a crash before main() or a failed `uv run` leave it unset."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    writes = behaviour in ("ok", "halt", "ops")
    fake_bin(bin_, "uv", (f'echo {code} > "$LAB2_EXIT_FILE"\n' if writes else "") + f"exit {code}\n")
    out = tmp_path / "out"
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "RUNNER_TEMP": str(tmp_path), "GITHUB_OUTPUT": str(out)}
    r = subprocess.run(["bash", "-e", "-c", step_script("Lab v2 run")], env=env, capture_output=True, text=True)
    assert r.returncode == code
    lines = out.read_text().splitlines()
    assert f"code={code}" in lines and (("finished=1" in lines) is finished)


def test_the_unfinished_step_restores_the_v2_folders_and_records_the_crash(tmp_path):
    """The "Lab v2 did not finish" step on a git checkout: partial writes in the three v2 folders are discarded, an
    untracked file there is removed, nothing else is touched, and the crash record is written (summary PAUSED, page
    re-rendered with the paused banner)."""
    repo = tmp_path / "repo"
    (repo / "analysis/system/lab_v2").mkdir(parents=True)
    for f in ("v2_crash.py", "v2_page.py"):
        shutil.copyfile(ROOT / "analysis/system/lab_v2" / f, repo / "analysis/system/lab_v2" / f)
    rep, site = repo / "reports/system/lab_v2", repo / "reports/forward_site/system/lab_v2"
    rep.mkdir(parents=True)
    s = dict(GOOD_SUMMARY)
    (rep / "summary.json").write_text(json.dumps(s, ensure_ascii=False))
    (rep / "decisions.csv").write_text("id,day\n")
    (repo / "data/system").mkdir(parents=True)
    (repo / "data/system/days.csv").write_text("v1\n")
    git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t"]
    subprocess.run(git + ["init", "-q"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-q", "-m", "base"], check=True)
    (rep / "decisions.csv").write_text("id,day\nS2,2026-11-09\n")          # a partial write of the killed run
    (rep / "lab_days.csv").write_text("day,settled_utc\n")                  # untracked
    (repo / "data/system/days.csv").write_text("v1 changed\n")              # outside the v2 folders: kept
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    fake_bin(bin_, "uv", "exit 2\n")                                         # uv fails: the python3 fallback runs
    fake_bin(bin_, "python3", f'exec "{sys.executable}" "$@"\n')
    script = step_script("Lab v2 did not finish").replace("${{ steps.lab2.outputs.code || 'none' }}", "none")
    env = {"PATH": f"{bin_}:/usr/bin:/bin", "GITHUB_RUN_ID": "42", "HOME": str(tmp_path)}
    r = subprocess.run(["bash", "-e", "-c", script], cwd=repo, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (rep / "decisions.csv").read_text() == "id,day\n" and not (rep / "lab_days.csv").exists()
    assert (repo / "data/system/days.csv").read_text() == "v1 changed\n"
    halt = (rep / "HALT.md").read_text()
    assert "lab v2 step did not finish (timeout or kill; exit code none)" in halt
    h = list(csv.DictReader(open(rep / "halts.csv")))
    assert len(h) == 1 and h[0]["run_id"] == "42" and len(h[0]["head_sha"]) == 40
    new = json.loads((rep / "summary.json").read_text())
    assert new["state"] == "PAUSED" and new["halted"] and new["asof_utc"] == s["asof_utc"] and new["halt_utc"]
    page = (site / "index.html").read_text()
    assert v2_page.PAUSED_AR in page and "المنظومة الأولى" not in page
    assert json.loads((site / "lab_v2.json").read_text())["state"] == "PAUSED"
    assert publish.lab2_lines(rep / "summary.json")[0] == "lab2_state,PAUSED"


def test_an_import_failure_halts_v2_through_the_crash_record(tmp_path):
    """§2.5 item 2: run_v2.py imports only the standard library unguarded. A copy of the lab v2 folder without the v1
    modules it needs (an ImportError, as a broken module would give) still writes HALT.md, halts.csv, the PAUSED
    summary, the page and its exit code (1) in cloud mode."""
    lab = tmp_path / "analysis/system/lab_v2"
    lab.mkdir(parents=True)
    for f in ("run_v2.py", "v2_crash.py", "v2_page.py", "v2paths.py"):
        shutil.copyfile(ROOT / "analysis/system/lab_v2" / f, lab / f)
    rep = tmp_path / "reports/system/lab_v2"
    rep.mkdir(parents=True)
    (rep / "summary.json").write_text(json.dumps(GOOD_SUMMARY, ensure_ascii=False))
    exit_file = tmp_path / "exit"
    env = dict(os.environ, GITHUB_ACTIONS="true", GITHUB_REF="refs/heads/main", GITHUB_RUN_ID="7",
               LAB2_EXIT_FILE=str(exit_file))
    r = subprocess.run([sys.executable, "-I", str(lab / "run_v2.py")], env=env, capture_output=True, text=True,
                       cwd=tmp_path)
    assert r.returncode == run_v2.EXIT_HALT, r.stderr
    assert exit_file.read_text().strip() == "1"
    assert "lab v2 could not import its modules: ModuleNotFoundError" in (rep / "HALT.md").read_text()
    assert json.loads((rep / "summary.json").read_text())["state"] == "PAUSED"
    page = (tmp_path / "reports/forward_site/system/lab_v2/index.html").read_text()
    assert v2_page.PAUSED_AR in page


def test_a_caught_exception_re_renders_the_client_page_paused(worlds, tmp_path):
    """crash() also rewrites lab_v2.json and index.html from the PAUSED summary (lab review MF2 b)."""
    PC, _ = worlds["C_v2_crashes_last"]
    page = (PC.site / "index.html").read_text()
    assert v2_page.PAUSED_AR in page and "forced crash" in json.loads((PC.site / "lab_v2.json").read_text())[
        "halt_reasons"][0]
    PB, _ = worlds["B_v2_always_crashes"]
    assert not (PB.site / "index.html").exists()             # no summary yet: nothing to show, no lab2 keys


def test_the_paused_banner_makes_no_claim_about_v1():
    """Amendment B2 item 3 (lab review MF4): the banner reads only «المختبر الثاني متوقف مؤقتًا»."""
    s = dict(GOOD_SUMMARY)
    running = v2_page.page_html(s)
    paused = v2_page.page_html(s | {"state": "PAUSED"})
    assert v2_page.PAUSED_AR == "المختبر الثاني متوقف مؤقتًا"
    assert v2_page.PAUSED_AR not in running and f'<p class="paused">{v2_page.PAUSED_AR}</p>' in paused
    assert "المنظومة الأولى" not in paused and "كالمعتاد" not in paused
    assert 'href="../"' in running                            # back to v1's lab page


def test_the_v1_lab_page_links_to_the_v2_section():
    """Amendment B2 item 2 (lab review MF3): the third v1 OPS edit, a link from reports/forward_site/system/index.html
    to system/lab_v2/, logged by v1's ops_changes.csv (and lab v2's)."""
    page = (ROOT / "reports/forward_site/system/index.html").read_text()
    assert '<a href="lab_v2/">' in page and "المختبر، الإصدار الثاني" in page
    assert "reports/forward_site/system/index.html" in v1run.OPS_FILES
    assert "reports/forward_site/system/index.html" in run_v2.OPS_FILES


def test_the_v1_part_of_the_workflow_is_unchanged():
    try:
        old = subprocess.run(["git", "-C", str(ROOT), "show", "origin/main:.github/workflows/system.yml"],
                             capture_output=True, text=True, check=True).stdout
    except subprocess.CalledProcessError:
        pytest.skip("origin/main not available")
    new = (ROOT / ".github/workflows/system.yml").read_text()
    i = new.index("      # Lab v2 (")
    j = new.index("      - name: Fail the job if the run halted or failed")
    assert new[:i] + new[j:] == old


# ---------------------------------------------------------------- the v1 publisher's lab2 keys (OPS edit)
L1 = {"green_ok": 1, "asof": "2026-11-03"}
L3 = {"asof": None, "mult": {b: (1.0, 0) for b in ("CPI", "FOMC", "NFP", "REOPEN", "N_ASIA", "N_LONDON", "N_NY")}}
LAB = {"state": "RUNNING", "days": 3, "n_paper": 1, "n_live": 0, "best_progress": 0.012, "live": []}


def site(tmp_path, summary):
    path = tmp_path / "reports/forward_site/system/VolMapSystem.csv"
    s = tmp_path / "reports/system/lab_v2/summary.json"
    s.parent.mkdir(parents=True, exist_ok=True)
    if summary is not None:
        s.write_text(summary if isinstance(summary, str) else json.dumps(summary))
    publish.write_system_csv(path, publish.system_csv("2026-11-14T03:20:00Z", L1, L3, LAB))
    return path.read_bytes()


GOOD = {"state": "RUNNING", "days": 5, "n_paper": 4, "best_progress": 0.0014705703464325502}
GOOD_SUMMARY = json.loads((Path(__file__).resolve().parents[2] / "judge_fixtures/synthetic_world/reports/system/lab_v2/"
                           "summary.json").read_text())


def test_lab2_keys_come_from_summary_json(tmp_path):
    data = site(tmp_path, GOOD)
    lines = data.decode().splitlines()
    assert lines[-5:] == ["lab2_state,RUNNING", "lab2_days,5", "lab2_n_paper,4", "lab2_best_progress,0.001",
                          f"end,{len(lines) - 1}"]
    kv = publish.parse_system_csv(data)
    assert kv is not None and kv["lab_n_paper"] == "1" and kv["lab_state"] == "RUNNING"
    assert all(ln.isascii() for ln in lines)
    base = publish.system_csv("2026-11-14T03:20:00Z", L1, L3, LAB)
    assert lines[:-5] == base[:-1]                         # every v1 line unchanged and in order


@pytest.mark.parametrize("bad", [None, "not json", "[]", {"state": "HALTED", "days": 1, "n_paper": 1,
                                                          "best_progress": 0.0},
                                 {"state": "RUNNING", "days": -1, "n_paper": 1, "best_progress": 0.0},
                                 {"state": "RUNNING", "days": 1.0, "n_paper": 1, "best_progress": 0.0},
                                 {"state": "RUNNING", "days": True, "n_paper": 1, "best_progress": 0.0},
                                 {"state": "RUNNING", "days": 1, "n_paper": 1, "best_progress": "0.1"},
                                 {"state": "RUNNING", "days": 1, "n_paper": 1},
                                 '{"state": "RUNNING", "days": 1, "n_paper": 1, "best_progress": NaN}'])
def test_lab2_keys_are_left_out_when_the_summary_is_missing_or_invalid(tmp_path, bad):
    data = site(tmp_path, bad)
    want = publish.encode_system_csv(publish.system_csv("2026-11-14T03:20:00Z", L1, L3, LAB))
    assert data == want


def test_a_write_outside_the_site_path_never_adds_keys(tmp_path):
    (tmp_path / "reports/system/lab_v2").mkdir(parents=True)
    (tmp_path / "reports/system/lab_v2/summary.json").write_text(json.dumps(GOOD))
    p = tmp_path / "x" / "VolMapSystem.csv"
    publish.write_system_csv(p, publish.system_csv("2026-11-14T03:20:00Z", L1, L3, LAB))
    assert b"lab2_" not in p.read_bytes()


def test_the_three_ops_edits_are_logged_by_v1():
    """§2.5 item 5 and Amendment B2 item 2: v1's run logs a row in reports/system/ops_changes.csv for each OPS file
    whose sha256 changed: system.yml, publish.py and the v1 lab page."""
    for f in (".github/workflows/system.yml", "analysis/system/publish.py", "reports/forward_site/system/index.html"):
        assert f in v1run.OPS_FILES


# ---------------------------------------------------------------- cloud mode guard (as v1)
def test_cloud_mode_runs_only_on_main_at_origin(monkeypatch):
    assert run_v2.cloud_refusal({}) is not None
    assert "main" in run_v2.cloud_refusal({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/system-v2"})
    monkeypatch.setattr(run_v2, "git", lambda *a: "abc")
    assert run_v2.cloud_refusal({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"}) is None
    monkeypatch.setattr(run_v2, "git", lambda *a: "abc" if a[-1] == "HEAD" else "def")
    assert "origin/main" in run_v2.cloud_refusal({"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main"})


def test_main_refuses_another_branch_before_writing_anything(monkeypatch):
    def snap():
        out = snapshot(ROOT / "reports", include_v2=True)
        for f in ("data/system/days.csv", "data/system/forecasts.csv"):
            p = ROOT / f
            out[f] = hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None
        return out
    before = snap()
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature")
    assert run_v2.main(["--no-fetch"]) != 0
    assert snap() == before


def test_registration_reads_the_registry_files_tracked_at_head():
    ids = run_v2.tracked_registry_ids()
    assert ids == {"S2", "S3", "S4", "S5"}
