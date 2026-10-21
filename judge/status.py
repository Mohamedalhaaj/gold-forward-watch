"""The judge's own parser of the system's status file reports/forward_site/system/VolMapSystem.csv (SYSTEM_V1_PREREG.md
§5 with Amendment A1 item 3; IMPLEMENTATION_REGISTER R-V1-41, R-V1-60)."""
import re

ORDER_HEAD = ("version", "asof_utc", "l1_green_ok", "l1_asof", "l3_asof")
ISO = re.compile(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ")


def parse(raw):
    """(parsed or None, problems). parsed = {"lines": [(key, value), ...]} without the header and end lines."""
    probs = []
    if raw.startswith(b"\xef\xbb\xbf"):
        probs.append("BOM")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        return None, [f"not UTF-8: {e}"]
    if "\r" in text:
        probs.append("CR in line ends")
    if not text.endswith("\n"):
        probs.append("no final newline")
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if not lines or lines[0] != "key,value":
        return None, probs + ["first line is not key,value"]
    if not lines[-1].startswith("end,") or lines[-1] != f"end,{len(lines) - 1}":
        return None, probs + [f"last line {lines[-1]!r} is not end,{len(lines) - 1}"]
    body = []
    for ln in lines[1:-1]:
        if "," not in ln or ln.startswith(","):
            probs.append(f"bad line {ln!r}")
            continue
        k, v = ln.split(",", 1)
        if not re.fullmatch(r"lab_live_\d+_title_ar", k) and not ln.isascii():
            probs.append(f"non-ASCII line {k}")
        body.append((k, v))
    keys = [k for k, _ in body]
    if len(set(keys)) != len(keys):
        probs.append("a key appears twice")
    d = dict(body)
    if d.get("version") != "1":
        probs.append(f"version {d.get('version')!r}")
    if not ISO.fullmatch(d.get("asof_utc", "")):
        probs.append(f"asof_utc {d.get('asof_utc')!r}")
    if d.get("l1_green_ok") not in ("0", "1"):
        probs.append(f"l1_green_ok {d.get('l1_green_ok')!r}")
    for k, v in body:
        if re.fullmatch(r"l3_m_\w+", k) and not re.fullmatch(r"\d+\.\d{4}", v):
            probs.append(f"{k} {v!r} is not %.4f")
        if (re.fullmatch(r"l3_n_\w+|lab2?_days|lab2?_n_paper|lab_n_live|lab_live_\d+_npost", k)
                and not re.fullmatch(r"\d+", v)):
            probs.append(f"{k} {v!r} is not a non-negative integer")
        if re.fullmatch(r"lab2?_best_progress", k) and not re.fullmatch(r"\d+\.\d{3}", v):
            probs.append(f"{k} {v!r} is not %.3f")
        if re.fullmatch(r"lab_live_\d+_title_ar", k):
            if not (1 <= len(v) <= 31 and all(_ar_letter(c) or c == " " or c.isdigit() for c in v)
                    and _ar_letter(v[0])):
                probs.append(f"{k}: the title breaks A1 item 3")
    return {"lines": body}, probs


def _ar_letter(c):
    o = ord(c)
    return 0x0621 <= o <= 0x064A and o != 0x0640
