#!/usr/bin/env python3
"""
upscale-door — install the working AMD upscaler stack into a game folder, reversibly.

    upscale-door doctor    <game-dir>
    upscale-door install   <game-dir>          # upscaling only
    upscale-door install   <game-dir> --nr     # also lay down the neural-rendering runtime
    upscale-door uninstall <game-dir>
    upscale-door verify    <game-dir>

THE RECIPE — every step is here because something failed without it on 2026-11-05:

1. `dxgi.dll` = OptiScaler's DLL (the AMDNR build). ONE door and ONE copy: two copies of the same hook
   library in one folder crashes the game before its first frame (measured, twice).

2. `nvngx.dll` = **a copy of the game's own signed `nvngx_dlss.dll`**. This is the step that makes DLSS
   appear in the game's menu on an AMD card — NVIDIA signed it, so the game's own check passes. Writing
   your own NGX core does NOT work: Control loads the file and never calls into it. That is the single
   most expensive lesson in this lane.

3. `OptiScaler.ini`: leave `Dx12Upscaler = auto`. With a neural runtime present this build picks the
   `_12` bridge backend by itself, and that is the ONLY backend neural rendering can run on. `FGOutput`
   is left to lsfg's frame generation: DLSSG needs Streamline DLLs and fails loudly without them.

4. With `--nr`: danielblnc's pass DLLs and weights go into `nr/`. AMDNR reads them from the game folder
   or from `[DlssNr] NrPath`. Neural rendering then needs `[DlssNr] Enabled = true` and a game restart.

REFUSALS ARE ABSOLUTE. An anti-cheat marker in the folder means nothing is written, and there is no
override flag — a live account got a warning inside a minute of an install into a game with
AntiCheatExpert. A foreign `dxgi.dll` is refused too: two DXGI proxies is a black screen with no message.
"""

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PAYLOAD = HERE / "payload"
CACHE = Path.home() / ".cache" / "upscale-door"
MANIFEST = ".upscale-door.json"

# ★ THE PAYLOAD IS NOT SHIPPED. OptiScaler and the AMDNR build are other people's work under their own
# licences, and 600 MB of binaries does not belong in a git repo. `fetch` downloads the release AMDNR
# publishes, checks it against the SHA-256 that release publishes, and unpacks it into a cache dir.
AMDNR_TAG = "Alpha0.3.5.8R16"
AMDNR_ZIP = "AMDNR-v0.3.5.8R16.zip"
RELEASE = f"https://github.com/3zwr1/AMD-NR---OptiScaler/releases/download/{AMDNR_TAG}"


def cmd_fetch(_=None) -> int:
    import urllib.request
    CACHE.mkdir(parents=True, exist_ok=True)
    sums = CACHE / "SHA256SUMS.txt"
    zpath = CACHE / AMDNR_ZIP
    print(f"fetching {AMDNR_ZIP} (~535 MB) from {RELEASE}")
    urllib.request.urlretrieve(f"{RELEASE}/SHA256SUMS.txt", sums)
    want = None
    for line in sums.read_text().splitlines():
        if AMDNR_ZIP in line:
            want = line.split()[0].strip("*")
    if not want:
        print("REFUSED: no checksum for that file in the release manifest")
        return 2
    urllib.request.urlretrieve(f"{RELEASE}/{AMDNR_ZIP}", zpath)
    got = sha(zpath)
    print(f"  sha256 {got}")
    if got != want:
        print(f"REFUSED: checksum mismatch — expected {want}")
        zpath.unlink(missing_ok=True)
        return 2
    print("  checksum matches the release")
    import subprocess as sp
    out = CACHE / "amd nr"
    out = CACHE / "AMDNR"
    if out.exists():
        import shutil as sh
        sh.rmtree(out)
    out.mkdir()
    sp.run(["7z", "x", "-y", f"-o{out}", str(zpath)], check=True, stdout=sp.DEVNULL)
    PAYLOAD.mkdir(exist_ok=True)
    (PAYLOAD / "OptiScaler.dll").unlink(missing_ok=True)
    import shutil as sh
    sh.copy2(out / "OptiScaler.dll", PAYLOAD / "OptiScaler.dll")
    if (PAYLOAD / "OptiScaler").exists():
        sh.rmtree(PAYLOAD / "OptiScaler")
    sh.copytree(out / "OptiScaler", PAYLOAD / "OptiScaler")
    if (out / "OptiScaler.ini").exists():
        sh.copy2(out / "OptiScaler.ini", PAYLOAD / "OptiScaler.ini")
    print(f"payload ready at {PAYLOAD} ({sum(f.stat().st_size for f in PAYLOAD.rglob('*') if f.is_file())/1e6:.0f} MB)")
    return 0

ANTICHEAT = [
    "easyanticheat", "easyanticheat_eos", "eac_launcher", "battleye", "beclient", "beservice",
    "anticheatexpert", "ace-game", "acestream", "xigncode", "xigncode3", "nprotect", "gameguard",
    "vanguard", "vgc", "vgk", "ricochet", "faceit", "mhyprot", "sguard", "punkbuster",
]

# ★ WHAT THE MATRIX TAUGHT US, AS A RULE RATHER THAN A DOC A HUMAN HAS TO READ.
# A tool that knows which combinations a human already proved wrong is worth more than one that says
# "install succeeded" and leaves the black screen to the user. Keyed by exe name because that is what the
# evidence is keyed to.
KNOWN = {
    "atomicheart-win64-shipping.exe": "the fancy build (dlss5-nr-amd-custom) black-screens this game on BOTH "
                                      "doors (dxgi.dll and winmm.dll); the plain build is stable",
    "gwt.exe": "the fancy build works here; neural rendering still stops at ZLUDA cuInit",
    "control_dx12.exe": "plain build; DLSS had to be unlocked with a signed nvngx.dll first",
}

NOT_THE_GAME = ("vc_redist", "dxsetup", "dxwebsetup", "ue4prereqsetup", "ue5prereqsetup",
                "dotnet", "oalinst", "vcredist", "crashreport", "uninstall", "setup")


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def exes(d: Path):
    out = []
    for p in d.rglob("*.exe"):
        if p.stat().st_size <= 1_000_000:
            continue
        if any(t in p.name.lower() for t in NOT_THE_GAME):
            continue
        out.append(p)
    return sorted(out, key=lambda p: p.stat().st_size, reverse=True)


def imports(target: Path):
    try:
        out = subprocess.run(["objdump", "-p", str(target)], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    return {m.group(1).lower() for m in re.finditer(r"DLL Name:\s*(\S+)", out)}


def anticheat_hits(d: Path):
    names = {p.name.lower() for p in d.rglob("*")}
    return sorted({m for m in ANTICHEAT if any(m in n for n in names)})


def is_ours(p: Path) -> bool:
    """Content, never size. A rebuilt DLL differs by kilobytes, and a size check once made a correct
    install look foreign — the kind of false alarm that gets a good install ripped out."""
    try:
        b = p.read_bytes()
    except OSError:
        return False
    return b"OptiScaler" in b or b"ngx-shim" in b or b"dxgi-spoof" in b


def signed_dlss(d: Path):
    """The signed DLSS runtime that doubles as nvngx.dll: the largest nvngx_dlss.dll in the folder."""
    # Prefer the GAME's own copy: the fancy package ships its own nvngx_dlss.dll inside OptiScaler/dlss5nr,
    # and using that as the provider works but is not the file the game itself was tested with.
    cands = [p for p in d.rglob("nvngx_dlss.dll") if "optiscaler" not in str(p).lower()]
    return max(cands, key=lambda p: p.stat().st_size) if cands else None


def cmd_doctor(d: Path) -> int:
    print(f"dir: {d}")
    if not d.is_dir():
        print("FAIL: not a directory")
        return 2
    found = exes(d)
    for e in found[:3]:
        print(f"exe: {e.relative_to(d)}  ({e.stat().st_size/1e6:.1f} MB)")
    if not found:
        print("exe: none over 1 MB — is this the right folder?")

    ac = anticheat_hits(d)
    print(f"anti-cheat: {', '.join(ac) if ac else 'none found'}" + ("  → REFUSED" if ac else ""))

    if found:
        api = set()
        for target in [found[0]] + sorted(d.glob("*.dll"))[:40]:
            got = imports(target)
            if got is None:
                api = None
                break
            api |= got
        if api is None:
            print("imports: objdump missing — cannot read the import table")
        else:
            gfx = sorted(a for a in api if a.startswith(("d3d11", "d3d12", "dxgi", "vulkan")))
            print(f"graphics imports: {', '.join(gfx) if gfx else 'none — not a D3D title?'}")

    if found:
        note = KNOWN.get(found[0].name.lower())
        if note:
            print(f"known: {note}")

    sgn = signed_dlss(d)
    print(f"signed provider for nvngx.dll: "
          f"{sgn.relative_to(d) if sgn else 'NOT FOUND — this game cannot be set up (no nvngx_dlss.dll)'}")

    for name in ("dxgi.dll", "winmm.dll", "nvapi64.dll", "nvngx.dll"):
        p = d / name
        if p.exists():
            note = "" if is_ours(p) or name == "nvngx.dll" else "  ⚠ not ours — install would refuse dxgi"
            print(f"{name}: present, {p.stat().st_size} bytes{note}")

    print("\nwould do: " + ("nothing (refused)" if ac else
                            "OptiScaler -> dxgi.dll, signed copy -> nvngx.dll, ini left to auto"))
    print("CANNOT do: force an engine to offer DLSS. nvngx.dll is what most games read; if the menu")
    print("still refuses, that engine checks something else and this tool will not fix it.")
    return 3 if ac else 0


def cmd_install(d: Path, want_nr: bool) -> int:
    ac = anticheat_hits(d)
    if ac:
        print(f"REFUSED: anti-cheat markers present ({', '.join(ac)}). Nothing written.")
        return 3
    if not PAYLOAD.is_dir() or not (PAYLOAD / "OptiScaler.dll").exists():
        print(f"REFUSED: payload missing at {PAYLOAD}")
        print("  run:  ./upscale-door.py fetch        (downloads AMDNR and verifies its checksum)")
        return 2
    signed = signed_dlss(d)
    if signed is None:
        print("REFUSED: no nvngx_dlss.dll in the folder to act as the signed provider.")
        print("  A DLSS-capable game ships one; without it DLSS will not appear, whatever we copy.")
        return 2

    man = {"dir": str(d), "files": {}, "created": {}}

    def put(src: Path, dst: Path, label: str = ""):
        prior = "absent"
        if dst.exists():
            if not is_ours(dst):
                raise SystemExit(f"REFUSED: {dst.name} exists and is not ours — another wrapper owns that name")
            prior = "ours"
        shutil.copy2(src, dst)
        rel = str(dst.relative_to(d))
        man["files"][rel] = {"prior": prior}
        man["created"][rel] = {"sha256": sha(dst), "bytes": dst.stat().st_size}
        print(f"  {dst.name:26} {dst.stat().st_size/1e6:7.1f} MB {label}")

    print("installing:")
    put(PAYLOAD / "OptiScaler.dll", d / "dxgi.dll", "(the door)")
    put(signed, d / "nvngx.dll", "(signed provider — this is the one that opens the menu)")

    # ★ THE DEPENDENCY FOLDER IS NOT OPTIONAL. Without `OptiScaler/`, the FFX DLLs are missing and the
    # upscaler silently falls back to FSR 2.2 — measured on Boundary, where the menu said "amd fidelity
    # dx12 needs extracted" and the image got worse, not better. Copy the whole folder.
    deps = PAYLOAD / "OptiScaler"
    if deps.is_dir():
        dst_deps = d / "OptiScaler"
        if dst_deps.exists():
            print("  OptiScaler/               kept (dependency folder already present)")
        else:
            import shutil as _sh
            _sh.copytree(deps, dst_deps)
            man["files"]["OptiScaler"] = {"prior": "absent"}
            print(f"  OptiScaler/               {sum(f.stat().st_size for f in dst_deps.rglob('*') if f.is_file())/1e6:7.1f} MB (FFX + deps)")

    ini = d / "OptiScaler.ini"
    if ini.exists():
        print("  OptiScaler.ini             kept (existing settings left alone)")
    elif (PAYLOAD / "OptiScaler.ini").exists():
        put(PAYLOAD / "OptiScaler.ini", ini)

    if want_nr:
        nr = d / "nr"
        nr.mkdir(exist_ok=True)
        files = sorted((PAYLOAD / "nr").glob("*")) if (PAYLOAD / "nr").is_dir() else []
        if not files:
            print("  WARNING: --nr given but payload/nr is empty; neural rendering will not arm")
        for f in files:
            put(f, nr / f.name, "(neural runtime)")
        print("  → set [DlssNr] Enabled = true in OptiScaler.ini, then restart the game")

    (d / MANIFEST).write_text(json.dumps(man, indent=1))
    print(f"\nmanifest: {d / MANIFEST}")
    print("next: launch the game. DLSS should be selectable where it was greyed.")
    print("If it is selectable but the picture ghosts, the upscaler is running without motion vectors:")
    print("press Insert and read the Upscaler / Input line in OptiScaler's own menu.")
    return 0


def cmd_uninstall(d: Path) -> int:
    mp = d / MANIFEST
    if not mp.exists():
        print(f"no manifest at {mp} — nothing this tool installed here")
        return 2
    m = json.loads(mp.read_text())
    for rel, rec in m["files"].items():
        p = d / rel
        if rec.get("prior") == "absent" and p.exists():
            # A manifest entry can name a DIRECTORY (the OptiScaler dependency folder); unlink would
            # fail on it and leave the user with a half-uninstalled game.
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            print(f"removed {rel}")
        else:
            print(f"left {rel} (it was ours before install)")
    nr = d / "nr"
    if nr.is_dir() and not any(nr.iterdir()):
        nr.rmdir()
    mp.unlink()
    print("manifest removed")
    return 0


def cmd_verify(d: Path) -> int:
    mp = d / MANIFEST
    if not mp.exists():
        print("no manifest — not installed by this tool")
        return 2
    m = json.loads(mp.read_text())
    bad = 0
    for rel, rec in m["created"].items():
        p = d / rel
        if not p.exists():
            print(f"MISSING {rel}")
            bad += 1
        elif sha(p) != rec["sha256"]:
            print(f"CHANGED {rel} (sha256 differs from the manifest — updated by something else?)")
            bad += 1
        else:
            print(f"ok {rel}")
    print("verdict:", "consistent" if not bad else f"{bad} problem(s)")
    return 0 if not bad else 1


def main(argv):
    # `fetch` needs no game directory, so it is dispatched before the arity check.
    if len(argv) >= 2 and argv[1] == "fetch":
        return cmd_fetch()
    if len(argv) < 3:
        print(__doc__)
        return 2
    cmd = argv[1]
    target = Path(argv[2]).expanduser().resolve() if len(argv) > 2 else None
    want_nr = "--nr" in argv[3:]
    table = {"doctor": cmd_doctor, "install": lambda d: cmd_install(d, want_nr),
             "uninstall": cmd_uninstall, "verify": cmd_verify, "fetch": lambda _d: cmd_fetch()}
    if cmd not in table:
        print(__doc__)
        return 2
    return table[cmd](target)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
