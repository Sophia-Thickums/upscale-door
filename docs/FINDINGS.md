# FINDINGS — 2026-11-05, the DLSS door on AMD/Linux

Everything here was measured on this box (RX 9070 XT, RADV 1.4.367 with our indirect-build patch,
GE-Proton 11-7, Wine/Proton with vkd3d-proton). Where something is inferred rather than observed it says so.

## What was tried, in order, and what each step proved

| # | attempt | result |
|---|---|---|
| 1 | OptiScaler as `nvngx_dlss.dll` (the house's existing install) | **never loaded.** Control greys DLSS before it asks for an upscaler, so nothing is called. |
| 2 | OptiScaler as `dxgi.dll` | **loads** (`working as dxgi.dll, system dll loaded`), FSR 4 proxy initialises (`InitFfxDx12_SR`, `InitFSR4Update`), and OptiScaler's own DLSS path is disabled on AMD: `Not running on Nvidia, disabling DLSS`. |
| 3 | OptiScaler's DXGI vendor spoof (`Dxgi=true`, explicit `SpoofedVendorId=0x10de`) | **hooked but did not convert**: `DxgiSpoofing::hkGetDesc … VendorId: 0x1002`. Control carries a compiled quirk (`Quirk: Dxgi spoofing disabled by default`) and there is no ini key to override it. |
| 4 | OptiScaler's registry / User32 / HAGS / factory-wrapping spoofs | no change to the menu. |
| 5 | A written NGX core (`nvngx.dll`, 32 exports) | **builds and loads**; `LoadLibrary → 0x6ffffde70000`, `GetProcAddress Init → 0x6ffffde700…c0`, log created. It is a valid NGX stand-in. |
| 6 | NGX core placed at the registry path Control reads (`HKLM\…\NVIDIA Corporation\Global\NGXCore` → `C:\Windows\System32`, both `nvngx.dll` and `_nvngx.dll`) | **the core loads into the game process** — but `Init` is never called. Control decides DLSS is unavailable before it ever asks for a core. |
| 7 | **Our own DXGI proxy** (`dxgi.dll`) that reports an NVIDIA adapter, OptiScaler moved to the `winmm` door | **works.** `GetDesc -> spoofed 0x10DE` through factory, `EnumAdapterByLuid` and `EnumAdapterByGpuPreference`. Control now believes it has an RTX 4090. |
| 8 | With the spoof live: Control's menu | **still greyed.** So the vendor is *not* the whole gate for this title. Something Northlight checks after the adapter is not satisfied. **Inferred, not observed** — the game has no log of its own. |
| 9 | Same stack in Boundary (UE5 RT benchmark) | the game **never loads a game-folder `dxgi.dll`** under Proton; `dxgi-spoof.log` is never created. UE titles get DXGI from the runtime. |
| 10 | NTE (with `dxgi.dll` + `nvngx.dll` installed) | **anti-cheat warning.** Files pulled immediately. Anti-cheat titles are now a hard refusal in the tool. |

## What this leaves true, and what it leaves open

**True:**
- A DXGI proxy can put an NVIDIA vendor id in front of any D3D12 game without touching the driver.
- An NGX core stand-in can be built with the public SDK headers and loads cleanly under Proton.
- FSR 4 is genuinely running in NTE (`amdxcffx64.dll` mapped in the game process, `lsfg-vk` on top) with
  **no mods at all** — GE-Proton's `fsr4` upgrade plus our launcher environment. This is tier 1 and it works.
- Frame generation is universal — the lsfg Vulkan layer hooks whatever the game does.

**Open:**
- No game has yet taken our NGX core and offered DLSS. Control refuses earlier than NGX; Boundary never
  loads the proxy; NTE is out on anti-cheat grounds.
- Making a game offer DLSS on AMD needs *its* gate satisfied, and that gate is per-engine and undocumented.
  Chasing it one title at a time is the definition of a research lane, not a product.
- Ray tracing: our driver work is conformance-clean and the DXR 1.2 mapping is measured, but no shipping
  game uses CLAS/PTLAS. Boundary reporting "hardware does not support RT" happened with **none of our
  DLLs loaded** — that is Boundary's own opinion of an AMD card through vkd3d, not our regression.

## The decision this produced

Ship what is provable:

1. **Tier 1 — FSR 4 wherever the game offers FSR.** Free, no mods, Proton does it. Verified in NTE.
2. **Tier 2 — frame generation everywhere.** lsfg-vk, universal.
3. **Tier 3 — DLSS-only titles: NOT SUPPORTED, and the README says so.** The pieces exist (spoof, core) and
   are kept in the tree as the start of the lane, not sold as a feature.

Anti-cheat refusal, backup manifests and `uninstall` are non-negotiable in anything that touches a game
folder — this morning is the reason.

---

## ★ SOLVED, later the same morning — the door is `nvngx.dll` = the game's OWN SIGNED DLSS DLL

Everything above was chasing the wrong component. The gate is not the vendor spoof and not a hand-written
NGX core. It is this, from OptiScaler's own install guide and the Linux guide that tested it on a 9070 XT:

```
cp nvngx_dlss.dll nvngx.dll        # the game's own NVIDIA-SIGNED DLSS library, renamed
```

The game loads `nvngx.dll`, finds a **signed** NVIDIA provider, and offers DLSS. Hand-writing an NGX core
fails for a reason no log states: the game loads the unsigned file and never calls into it — a DLL that
is never used looks identical to one that was never found.

### The working recipe (verified in Control, 2026-11-05 09:53)

| step | why |
|---|---|
| `dxgi.dll` = OptiScaler (AMDNR build) | the hook, ONE copy — two copies crash the game before its first frame |
| `nvngx.dll` = copy of the game's signed `nvngx_dlss.dll` | **this is what makes DLSS appear in the menu** |
| `OptiScaler.ini`: `Dx12Upscaler = auto` | with a neural runtime present, auto picks the `_12` bridge, the only backend NR can run on |
| `FGOutput = nofg` | DLSSG wants Streamline DLLs; lsfg owns frame generation here |
| launch option `WINEDLLOVERRIDES="dxgi=n,b"` | otherwise Wine loads its own DXGI and the mod never enters the process |

**Proof it works, from the live log:**

```
[SR_INPUTS] provider=ffx render=1969x1107 upscale=2560x1440 mv=1969x1107 depth=1969x1107
[FIRST-EVAL] end provider= … elapsed_ms=13 result=ok
GPU: 100 % busy, 249 W
```

DLSS selectable in the game's own menu, FSR 4 doing a real 77 % render scale, frame generation on top.

### Neural rendering: loaded, selected, and stalled

Daniel 0.8.0 is now installed and chosen: the host DLL is mapped in the game process, `[NHUB080-SEL] 0.8.0
page=controls refusal=none`, control writes read back. But:

```
[NHUB080-PROGRESS] status=d3d12 net: state 0, frames recorded 0, passed through 0
[NHUB080-NR-STALL] swapchain_api=D3D12 host_present=seen
[NR-STATE] runtime=daniel080 state=off reason=host-stall
```

The host **sees the game presenting and captures no frames.** The most likely cause is its D3D12 capture
path meeting vkd3d's translation instead of native D3D12. Untried: the lmxxf runtime, which AMDNR ships in
newer releases with a different capture path (needs a ~1 GB download).

### The honest scope for the tool

`upscale-door` now does the recipe that works. What it buys: **DLSS in the menu + FSR 4 + frame generation,
per game, with an exact undo.** What it does not buy: neural rendering, and never a game whose engine
refuses before it consults any of these files.

### Published

`https://github.com/Sophia-Thickums/upscale-door` — public, MIT, four files, no vendored binaries.
`fetch` downloads AMDNR's release and verifies the SHA-256 that release publishes (`b66db805…`, matched)
before unpacking; `payload/` is gitignored. Verified end to end before the push: fetch → doctor → install →
verify → uninstall, folder returned to its original two files.

The README states the three limits in the same voice as the wins: games that never had DLSS, neural
rendering (both runtimes blocked, with reasons), and bare benchmark shells (Boundary's missing Agility SDK
plus Wine's absent `IsDeveloperModeEnabled`).
