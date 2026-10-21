"""J1 (independent re-download) with a fake transport, and J9 (Amendment B1 item 2, IMPLEMENTATION_REGISTER §13) with a
local mock HTTP server standing in for Twelve Data. No real key and no real network: the key is a fake string, and
the test asserts it travels only in the Authorization header and is never written or printed."""
import json
import lzma
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pandas as pd
import pytest

from judge import checks, dukascopy, store
from judge.common import parse_utc, read_dicts

FAKE_KEY = "FAKE-KEY-0123456789abcdef"


# ======================================================================== J1
class FakeTransport:
    def __init__(self, world, mode):
        self.world, self.mode, self.urls = world, mode, []

    def get(self, u):
        self.urls.append(u)
        parts = u.split("/")
        y, m0, d, side = int(parts[-4]), int(parts[-3]), int(parts[-2]), parts[-1].split("_")[0]
        day = f"{y:04d}-{m0 + 1:02d}-{d:02d}"
        base = self.world / ("data/system/lab_v2/lookback" if y == 2026 and m0 + 1 <= 8 else "data/system")
        b = store.raw_path(base, day, side).read_bytes()
        mode = self.mode.get((day, side), "same")
        if mode == "fail":
            return 503, b""
        if mode == "revised":
            r = dukascopy.records(b).copy()
            r["c"][700] += 1
            return 200, lzma.compress(r.tobytes(), format=lzma.FORMAT_ALONE)
        if mode == "recompressed":     # the same records in another LZMA stream: equal arrays, different bytes
            return 200, lzma.compress(dukascopy.records(b).tobytes(), format=lzma.FORMAT_ALONE, preset=1)
        return 200, b


def test_j1_same_revised_known_and_unverified(tmp_path, fixture_world):
    now = parse_utc("2026-12-05T13:10:00Z")
    tr = FakeTransport(fixture_world, {("2026-12-04", "ASK"): "revised", ("2026-12-03", "BID"): "fail",
                                       ("2026-12-03", "ASK"): "recompressed"})
    c = checks.j1(fixture_world, tmp_path, now, tr, sample=0, max_new_days=2)
    assert c.status == "warning" and c.reasons == ["j1_revised"]
    log = read_dicts(tmp_path / checks.J1_LOG)
    # the system's own store first, newest day first
    assert [(r["store"], r["day"], r["side"], r["result"], r["http"]) for r in log] == [
        ("v1", "2026-12-04", "BID", "same", "200"), ("v1", "2026-12-04", "ASK", "revised", "200"),
        ("v1", "2026-12-03", "BID", "unverified", "503"), ("v1", "2026-12-03", "ASK", "same", "200")]
    assert len(read_dicts(tmp_path / checks.KNOWN)) == 1
    assert all("datafeed.dukascopy.com/datafeed/XAUUSD/2026/11/0" in u for u in tr.urls)
    # the next run: the revised side is known (no new WARNING); the day with an unverified side is new again
    tr2 = FakeTransport(fixture_world, {("2026-12-04", "ASK"): "revised"})
    c2 = checks.j1(fixture_world, tmp_path, now + pd.Timedelta(days=1), tr2, sample=1, max_new_days=1)
    assert c2.status == "ok"
    log2 = [(r["day"], r["side"], r["result"]) for r in read_dicts(tmp_path / checks.J1_LOG)[4:]]
    assert log2 == [("2026-12-03", "BID", "same"), ("2026-12-03", "ASK", "same"), ("2026-12-04", "BID", "same"),
                    ("2026-12-04", "ASK", "known")]


def test_j1_failed_downloads_are_unverified_not_a_mismatch(tmp_path, fixture_world):
    class Down:
        def get(self, u):
            return None
    c = checks.j1(fixture_world, tmp_path, parse_utc("2026-12-05T13:10:00Z"), Down(), sample=0, max_new_days=3)
    assert c.status == "ok" and c.unverified


# ======================================================================== J9 mock server
class Mock(BaseHTTPRequestHandler):
    script = []          # list of (status, body bytes)
    seen = []

    def do_GET(self):
        Mock.seen.append({"path": self.path, "auth": self.headers.get("Authorization")})
        status, body = Mock.script.pop(0) if Mock.script else (500, b"")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.fixture()
def server():
    srv = HTTPServer(("127.0.0.1", 0), Mock)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    Mock.script, Mock.seen = [], []
    yield srv
    srv.shutdown()


def opener_for(srv):
    def op(req, timeout):
        u = urllib.parse.urlsplit(req.full_url)
        assert u.netloc == "api.twelvedata.com" and u.path == "/time_series"
        local = f"http://127.0.0.1:{srv.server_address[1]}{u.path}?{u.query}"
        r2 = urllib.request.Request(local, headers=dict(req.header_items()))
        return urllib.request.urlopen(r2, timeout=timeout)
    return op


def duka_hour_closes(world, day):
    v1 = store.Store(world / "data/system")
    st = v1.status(None)
    fr = {s: dukascopy.frame(v1.body(day, s, st[(day, s)]), day).set_index("ts") for s in ("BID", "ASK")}
    j = fr["BID"].join(fr["ASK"], lsuffix="_b", rsuffix="_a", how="inner")
    j = j[(j.vol_b > 0) & (j.vol_a > 0)]
    out = {}
    for h in range(24):
        t = pd.Timestamp(day, tz="UTC") + pd.Timedelta(hours=h)
        w = j[(j.index >= t) & (j.index < t + pd.Timedelta(hours=1))]
        if len(w):
            out[t] = (w.c_b.iloc[-1] + w.c_a.iloc[-1]) / 2
    return out


def td_body(closes, offset):
    vals = [{"datetime": t.strftime("%Y-%m-%d %H:%M:%S"), "open": "1", "high": "1", "low": "1",
             "close": f"{c + offset:.5f}"} for t, c in sorted(closes.items(), reverse=True)]
    # one bar of the next day: outside [D, D + 1 day), ignored whatever the endpoint's inclusivity
    vals.insert(0, {"datetime": (max(closes) + pd.Timedelta(hours=1)).strftime("%Y-%m-%d 00:00:00"), "close": "1"})
    return json.dumps({"meta": {"symbol": "XAU/USD"}, "values": vals, "status": "ok"}).encode()


def test_j9_no_key_sends_nothing(tmp_path, fixture_world, server):
    c = checks.j9(fixture_world, tmp_path, parse_utc("2026-11-04T13:10:00Z"), opener=opener_for(server),
                  sleep=lambda s: None, env={})
    assert c.status == "ok" and Mock.seen == []
    row = read_dicts(tmp_path / checks.CS)[0]
    assert (row["day"], row["result"], row["reason"], row["credits"]) == ("2026-11-03", "unverified", "no key", "0")


def test_j9_ok_exceeds_and_the_warning(tmp_path, fixture_world, server, capsys):
    env = {"TWELVEDATA_API_KEY": FAKE_KEY}
    d1, d2 = "2026-11-03", "2026-11-04"
    Mock.script = [(200, td_body(duka_hour_closes(fixture_world, d1), 0.10))]
    c = checks.j9(fixture_world, tmp_path, parse_utc("2026-11-04T13:10:00Z"), opener=opener_for(server),
                  sleep=lambda s: None, env=env)
    assert c.status == "ok"
    row = read_dicts(tmp_path / checks.CS)[-1]
    assert row["result"] == "ok" and int(row["n_hours"]) >= 20 and row["credits"] == "1"
    assert abs(float(row["median_abs_usd"]) - 0.10) < 1e-6
    q = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(Mock.seen[0]["path"]).query))
    assert q == {"symbol": "XAU/USD", "interval": "1h", "timezone": "UTC", "start_date": "2026-11-03 00:00:00",
                 "end_date": "2026-11-04 00:00:00"}
    assert Mock.seen[0]["auth"] == f"apikey {FAKE_KEY}" and FAKE_KEY not in Mock.seen[0]["path"]
    # the same day again: no request, nothing new
    n = len(read_dicts(tmp_path / checks.CS))
    checks.j9(fixture_world, tmp_path, parse_utc("2026-11-04T15:10:00Z"), opener=opener_for(server),
              sleep=lambda s: None, env=env)
    assert len(Mock.seen) == 1 and len(read_dicts(tmp_path / checks.CS)) == n
    # two consecutive checked days above the limits -> WARNING (the first exceeding day alone is descriptive)
    Mock.script = [(200, td_body(duka_hour_closes(fixture_world, d2), 0.75))]
    c = checks.j9(fixture_world, tmp_path, parse_utc("2026-11-05T13:10:00Z"), opener=opener_for(server),
                  sleep=lambda s: None, env=env)
    assert c.status == "ok" and read_dicts(tmp_path / checks.CS)[-1]["result"] == "exceeds"
    Mock.script = [(200, td_body(duka_hour_closes(fixture_world, "2026-11-05"), -6.0))]
    c = checks.j9(fixture_world, tmp_path, parse_utc("2026-11-06T13:10:00Z"), opener=opener_for(server),
                  sleep=lambda s: None, env=env)
    assert c.status == "warning" and c.reasons == ["j9_price"]
    txt = (tmp_path / checks.CS).read_text()
    out = capsys.readouterr()
    assert FAKE_KEY not in txt and FAKE_KEY not in out.out + out.err
    assert all(FAKE_KEY not in e for e in c.evidence)


@pytest.mark.parametrize("script,reason,credits", [
    ([(429, b'{"code":429,"message":"x"}')], "quota", "1"),
    ([(200, b'{"status":"error","code":429,"message":"x"}')], "quota", "1"),
    ([(200, b'{"status":"error","code":401,"message":"bad key"}')], "api 401", "1"),
    ([(200, b"<html>not json</html>")], "bad response", "1"),
    ([(500, b""), (502, b"")], "http 502", "2"),
    ([(404, b"")], "http 404", "1"),
    ([(200, b'{"status":"ok","values":[{"datetime":"2026-11-03 10:00:00","close":"nan"}]}')], "bad response", "1"),
    ([(200, b'{"status":"ok","values":[{"datetime":"2026-11-04 10:00:00","close":"4000"}]}')], "no common hour",
     "1"),
])
def test_j9_failures_are_unverified(tmp_path, fixture_world, server, script, reason, credits):
    Mock.script = list(script)
    slept = []
    c = checks.j9(fixture_world, tmp_path, parse_utc("2026-11-04T13:10:00Z"), opener=opener_for(server),
                  sleep=slept.append, env={"TWELVEDATA_API_KEY": FAKE_KEY})
    row = read_dicts(tmp_path / checks.CS)[-1]
    assert c.status == "ok" and (row["result"], row["reason"], row["credits"]) == ("unverified", reason, credits)
    assert len(Mock.seen) == int(credits) <= 2
    if credits == "2":
        assert slept == [20]
    assert FAKE_KEY not in (tmp_path / checks.CS).read_text()


def test_j9_retry_then_success(tmp_path, fixture_world, server):
    Mock.script = [(503, b""), (200, td_body(duka_hour_closes(fixture_world, "2026-11-03"), 0.0))]
    c = checks.j9(fixture_world, tmp_path, parse_utc("2026-11-04T13:10:00Z"), opener=opener_for(server),
                  sleep=lambda s: None, env={"TWELVEDATA_API_KEY": FAKE_KEY})
    row = read_dicts(tmp_path / checks.CS)[-1]
    assert c.status == "ok" and row["result"] == "ok" and row["credits"] == "2" and float(row["max_abs_usd"]) < 1e-6


def test_judge_source_reads_the_key_only_from_the_environment(root):
    src = "\n".join(p.read_text() for p in (root / "judge").rglob("*.py") if "vendor" not in p.parts)
    assert "security find-generic-password" not in src and "keychain" not in src.lower().replace(
        "never reads the macos keychain", "")
    assert src.count("TWELVEDATA_API_KEY") >= 1
    assert "apikey=" not in src            # never in a query string
