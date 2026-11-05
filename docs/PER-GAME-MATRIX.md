# PER-GAME MATRIX — what works, on this box, measured 2026-11-05

Plain English first: **the stack works, game by game, and where it works the picture and the frame rate
both improve.** Where it doesn't, the reason is recorded rather than guessed.

Two builds exist and they are not interchangeable:

- **PLAIN** — AMDNR R16 OptiScaler. Menu without a Neural tab. Runs in every D3D12 game tried.
- **FANCY** — `dlss5-nr-amd-custom` (RedDuke). Same base plus its own neural-rendering runtime, async
  mode, DLSS SR/RR emulation. Bigger menu. Black-screens some games.

| game | engine / API | works | build | what you get |
|---|---|---|---|---|
| **Control** | Northlight, D3D12 | ✅ | PLAIN | DLSS **unlocked in the game's own menu**; FSR 4 at a real 77 % render scale (`render=1969x1107 → 2560x1440`); lsfg 2×; GPU 100 %/249 W |
| **Ghostwire: Tokyo** | UE4, D3D12 | ✅ | FANCY | FSR 4 + lsfg; menu with Neural tab; **NR stalls** (see below) |
| **Atomic Heart** | UE4, D3D12 | ✅ | **PLAIN only** | FSR 4 + lsfg. FANCY black-screens on **both** doors (`dxgi.dll` and `winmm.dll`) — the files are parked in `_fancy-off/` |
| **Neverness to Everness** | UE5, D3D12 | ❌ | — | ACE anti-cheat warns on the proxy, every time. Files pulled, folder clean |
| **Genshin Impact** | DX11, mhyprot | ❌ | — | No DLSS/FSR to unlock at all, and kernel anti-cheat |
| **Chrono Trigger** | Cocos2d, **OpenGL**, 32-bit | ❌ | — | No D3D present for any hook to attach to. Needs the ReShade+Feeder route, which has no AMD build |
| emulators | — | ❌ | — | **Ryan does not emulate on this machine** (his call, standing) |

## The two things that still don't work, and exactly why

**1. Neural rendering — blocked at the AMD driver bridge.**
The full chain loads: OptiScaler fork → `dlss5nr_host.exe` → `amdhip64_7.dll` → `libdlss5nr_hip_bridge.so`.
Then ZLUDA's `cuInit` returns **801**, and the project's own troubleshooting table says what that means:

> "cuInit failed: 801" — the bridge could not load `libamdhip64.so.7` (not installed, or **not visible in
> Steam's container**)

**CORRECTION, made the same hour:** the container is *not* the problem. Read from the running game's own
namespace, `/proc/<pid>/root/opt/rocm/lib/libamdhip64.so.7` resolves — `/opt` is mounted inside it. And the
one function the bridge reports missing (`hipExternalMemoryGetMappedMipmappedArray`) is **declared in ROCm
7.2.4's headers but exported by no library**, i.e. normal for this install, not a symptom.

So the honest state is: **cause not yet identified.** What is ruled out: the library's presence, the container's
mounts, the GPU (gfx1201 is supported and seen by ROCm), the model build (310.9.16.0), and the preload (the
launcher sets it, and the failure message changed from "no handle file" to `cuInit` once it did).

What is left, untested: the difference between a game launched by **Steam** (inside pressure-vessel) and one
launched by **Proton directly** — the two have different namespaces even though `/opt` is visible. Testing
that requires one more launch, which Ryan has ruled out, so it stays open rather than guessed at.

**2. FANCY build in Atomic Heart.** Black screen with our proxy mapped and the card idle at 10 %: the hook
takes the swapchain and never presents. Door-independent (tried `dxgi.dll` and `winmm.dll`). PLAIN is stable
there, so the game keeps PLAIN.

## What is genuinely proven

- **DLSS can be made to appear in a game's own menu on an AMD card** — by copying the game's signed
  `nvngx_dlss.dll` to `nvngx.dll`. Verified in Control.
- **FSR 4 renders behind it**, at a real sub-native render scale, with frame generation on top — Control,
  Ghostwire, Atomic Heart.
- **It is reversible** — `upscale-door` installs with a manifest and uninstalls byte-exact.
- **Anti-cheat is refused before anything is written**, with no override flag, and the two games that
  refused (NTE twice) are the reason that rule has no exemption.
