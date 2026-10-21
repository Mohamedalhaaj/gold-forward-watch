"""sha256 manifests (`<sha256>  <path>` lines): the system's FROZEN.sha256 / FROZEN_V2.sha256 and the judge's own
FROZEN_JUDGE.sha256. The judge only compares hashes; it never imports or runs a file it hashes."""
from pathlib import Path

from . import gitio
from .common import sha256_file


def parse(text):
    out = {}
    for ln in (text or "").splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        parts = ln.split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            out[parts[1].strip().lstrip("*")] = parts[0].lower()
    return out


def read_manifest(repo, commit, rel):
    """The manifest at `commit` (git), or in the working tree when commit is None."""
    if commit:
        b = gitio.show_bytes(str(repo), commit, rel)
        return parse(b.decode("utf-8", "replace")) if b is not None else None
    p = Path(repo) / rel
    return parse(p.read_text(encoding="utf-8")) if p.exists() else None


def resolve(repo, rel_manifest, path):
    """A manifest entry's file: paths are taken relative to the repository root, else to the manifest's folder."""
    repo = Path(repo)
    for cand in (repo / path, (repo / rel_manifest).parent / path):
        if cand.exists():
            return cand
    return None


def verify(repo, rel_manifest, pinned):
    """J4 for one pinned manifest: (problems, n_entries). Every pinned entry is unchanged in the current manifest,
    none was removed, and every named file exists with that sha256."""
    probs = []
    cur = read_manifest(repo, None, rel_manifest)
    if cur is None:
        return [f"{rel_manifest}: missing"], len(pinned)
    for p, h in pinned.items():
        if p not in cur:
            probs.append(f"{rel_manifest}: entry {p} was removed")
        elif cur[p] != h:
            probs.append(f"{rel_manifest}: entry {p} changed")
        f = resolve(repo, rel_manifest, p)
        if f is None:
            probs.append(f"{p}: missing")
        elif sha256_file(f) != h:
            probs.append(f"{p}: sha256 differs from the pinned manifest")
    return probs, len(pinned)
