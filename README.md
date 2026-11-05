# upscale-door

Install the working AMD upscaler stack into a game folder — reversibly, with a refusal list that has no
override.

```
./upscale-door.py doctor    <game-dir>
./upscale-door.py install   <game-dir>          # upscaling + DLSS in the game's own menu
./upscale-door.py install   <game-dir> --nr     # also lay down the neural-rendering runtime
./upscale-door.py uninstall <game-dir>
./upscale-door.py verify    <game-dir>
```

## What's in here

| file | what it is |
|---|---|
| `upscale-door.py` | the installer: `fetch`, `doctor`, `install`, `uninstall`, `verify` |
| `sophia-nr` | the same stack for **non-Steam** games: a Proton launcher that preloads the HIP bridge and sets the overrides `launch.sh` would set from Steam |
| `docs/PER-GAME-MATRIX.md` | what worked, what didn't, and why — three games working, three walls with named causes |
| `docs/FINDINGS.md` | the full investigation, attempt by attempt, including the two dead ends worth not repeating |

## Replicating this

1. `./upscale-door.py fetch` — downloads AMDNR's release and verifies its published SHA-256.
2. `./upscale-door.py doctor <game-dir>` — says whether the game can be set up at all (it refuses when
   there is no signed `nvngx_dlss.dll` to use as the provider).
3. `./upscale-door.py install <game-dir>`.
4. Launch option in Steam: `WINEDLLOVERRIDES="dxgi=n,b" %command%`.
5. In game: pick DLSS at a quality **below Native** — a 1:1 request gives the upscaler nothing to do.

## What this actually does — and the trick is not what anyone expects

It makes **DLSS appear in a game's own graphics menu on an AMD card**, and puts **FSR 4** behind it.

Not a hand-written NGX core, and not a vendor spoof: both were built and both fail (the game accepts an
unsigned core and never calls into it; the spoof makes the adapter NVIDIA and the menu stays grey). The
thing that works is one copy:

```
cp <the game's own nvngx_dlss.dll>  nvngx.dll
```

The game loads `nvngx.dll`, finds an **NVIDIA-signed** DLSS library, and offers DLSS. OptiScaler, sitting
on `dxgi.dll`, intercepts the upscale call and answers it with FSR 4.

Measured on Control, 2026-11-05:

```
[SR_INPUTS] provider=ffx render=1969x1107 upscale=2560x1440 mv=1969x1107 depth=1969x1107
[FIRST-EVAL] result=ok
GPU 100 % busy, 249 W
```

DLSS selectable in the game's own menu, a real 77 % render scale, frame generation (lsfg) on top.

## The four files and one flag

| what | why |
|---|---|
| `dxgi.dll` = OptiScaler | the hook. **One copy only** — two copies of this library in one folder crashes the game before its first frame |
| `OptiScaler/` folder | the FFX dependency set. **Without it the upscaler silently falls back to FSR 2.2** and the menu says *"amd fidelity dx12 needs extracted"* |
| `nvngx.dll` = the game's signed `nvngx_dlss.dll` | the step that opens the menu |
| `OptiScaler.ini` | `Dx12Upscaler = auto`, `FGOutput = nofg` — frame generation is lsfg's job here |
| launch option `WINEDLLOVERRIDES="dxgi=n,b" %command%` | without it Wine loads its own DXGI and the mod never enters the process |

## Refusals (there is no override flag)

- **Anti-cheat.** EasyAntiCheat, BattlEye, AntiCheatExpert, XignCode, nProtect, Vanguard, Ricochet,
  **mhyprot** (HoYoverse), and friends. A shim there is a cheat as far as the kernel driver is concerned.
  Measured the only good way: a live account got a warning within a minute.
- **A foreign `dxgi.dll`.** Two DXGI proxies in one folder is a black screen with no message.
- **No `nvngx_dlss.dll`.** No signed provider, so DLSS will not appear whatever we copy. `doctor` says so
  before anything is written.

## What it cannot do

- **Games that never had DLSS.** There is no option to reveal — Genshin, for one, never had one.
- **Neural rendering.** Both runtimes were tried on 2026-11-05 and both are blocked on this stack:
  danielblnc's 0.8.0 host loads and selects, then records **zero frames** under vkd3d's D3D12
  (`reason=host-stall`); lmxxf needs AMD's **Windows** HIP runtime (`amdhip64_6/7.dll`), which does not
  exist under Proton and crashed the menu the moment it was used.
- **Bare benchmark shells.** Boundary ships no Agility SDK; OptiScaler's upgrade path needs Windows'
  `IsDeveloperModeEnabled`, which Wine lacks, so the process aborts. Real games ship their own.

## Undo

`install` writes `.upscale-door.json` recording each file's prior state and its hash. `uninstall` removes
only what it added — including the `OptiScaler/` directory — and `verify` re-hashes against the manifest,
so "still installed" is a fact rather than a memory.

## Status

The upscaler half works and is proven in a commercial game. The neural-rendering half is blocked for
reasons recorded above, not for want of trying.
