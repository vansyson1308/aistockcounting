# Gate 0A — Revision 2: Executive Report (A–Z)

Run date: 2026-08-25 · Branch: `gate0a-revision-2` (from `main` @ `1c1fd7a` after PR #2 merge) · Status: **BLOCKED — NEW blocker (see §K)** · Machine record: [`verdict.json`](verdict.json)

---

## A. Executive verdict

Gate 0A Revision 2 could **not** be executed end-to-end, and the reason is
**new, fresh, and independently verified — not the Revision 1 record
restated**. The Revision 2 authorization designates *the owner's local
machine* as the execution workstation. This session demonstrably does not run
on that machine and has no reachable channel to it: it executes in the
account's **only** Claude Code environment — an `anthropic_cloud` container
with **no NVIDIA silicon at the PCI level** and an egress policy whose
gateway **rejects CONNECT to huggingface.co and cdn-lfs.huggingface.co with
403** (the sole host of SoccerTrack v2). No self-hosted environment is
registered on the account, no local agent/session is reachable, and the one
local-bridge session on record fails with `computer_unreachable`. Cloud
purchases are prohibited by the task constraints. Everything that could be
done honestly was done: the mandated fresh re-verification (§2), the git
checkpoint (§3), the frozen-contract re-verification (§4), a live Stage A
download attempt (§5), the exhaustive §22 surface search, and this report.
**No result was fabricated; no threshold was touched.**

## B. Mandate and rules honored

Revision 2 (§§1–29): re-verify the environment from scratch — do **not**
accept the old blocker without fresh probing; complete the git checkpoint;
keep the contract frozen; execute the full real pipeline if any authorized
surface permits; otherwise report a **new** blocker with hardware evidence.
Constraints honored: no cloud/paid purchases, no fabricated or simulated
results, no threshold/TEST changes, no unrelated-file modifications, large
data/caches gitignored.

## C. §2 fresh environment re-verification (executed 2026-08-25, from scratch)

Raw outputs: [`raw_probe_hardware.txt`](raw_probe_hardware.txt),
[`raw_probe_network.txt`](raw_probe_network.txt). Machine-readable:
[`environment_verification.json`](environment_verification.json).

| Probe | Result |
|---|---|
| `nvidia-smi` / `nvcc` | command not found / absent |
| `/dev/nvidia*`, `/dev/dri`, `/dev/dxg` | all absent (no passthrough of any kind) |
| `/proc/driver/nvidia` | absent |
| **PCI vendor scan** (`/sys/bus/pci/devices/*/vendor`) | **no `0x10de` (NVIDIA) device — no GPU silicon exists in this machine**, not merely missing drivers |
| CPU / RAM / disk | 4-core Intel Xeon @ 2.80 GHz / 16.5 GB / 30 GB free on `/dev/vda` (virtual disk) |
| Host identity | hostname `vm`, kernel `Linux 6.18.44-fc-v21` — managed cloud container |
| `https://huggingface.co` | `CONNECT tunnel failed, response 403` |
| `https://cdn-lfs.huggingface.co` | `CONNECT tunnel failed, response 403` |
| git transport to HF dataset | `git ls-remote` → same CONNECT 403 |
| Proxy self-report | `/__agentproxy/status` logs `"gateway answered 403 to CONNECT (policy denial or upstream failure)"` for both HF hosts at 2026-08-25T02:06:51Z — a **policy** state, not an outage |
| Control hosts (proxy works) | `pypi.org` → 200; `github.com`, `storage.googleapis.com` → answer |

## D. §22 exhaustive execution-surface search (the new finding)

Full record: [`execution_surface_search.md`](execution_surface_search.md).
Surfaces enumerated on 2026-08-25: (1) this container — no GPU at silicon
level; (2) account environments via `list_environments` — **exactly one**,
`env_01BWXwEeu7xncKhu95swQPwA` (`anthropic_cloud`), i.e. no self-hosted/local
runner and no GPU environment to create a session in; (3) reachable
agents/sessions — none (`ListAgents` empty; account session list shows only
cloud sessions plus one Cowork local bridge whose last init failed
`computer_unreachable`); (4) dataset egress — blocked by policy (above), all
known mirrors previously verified blocked and unchanged; (5) purchased
compute — prohibited. **Conclusion: the local-machine authorization has no
executable channel from this session.**

## E. §3 git checkpoint (completed)

1. PR #2 verified: head `32e7d35`, `mergeable_state: clean`, all five checks
   green (`ml`, `backend`, `frontend`, `docker-build`, GitGuardian).
2. Marked ready for review, merged to `main` with a merge commit →
   `main` @ `1c1fd7a9136a3d5c6729574cc8596f41145a5de4`.
3. Branch **`gate0a-revision-2`** created from that merged `main`; all
   Revision 2 artifacts live on it. PR #2's watch subscription and check-in
   trigger were retired.

## F. §4 frozen contract (re-verified byte-identical)

Record: [`frozen_contract.json`](frozen_contract.json).
`ml/gate0a/thresholds.yaml` sha256
`0d8bb0d66871277fe07becc40e7908f302f89e612fddadd6fec988d4bdbc50bf` —
**identical to the hash frozen before any experiment**. Split manifest
(`92c4390c…`) and dense-eval manifest (`1ad90765…`) unchanged. No threshold
edits, no TEST contact, no cherry-picking, no manual fixes, no GT identity as
pipeline input — attested in the record.

## G. §5 Stage A download attempt (executed live, verbatim failure)

Raw: [`raw_probe_stage_a.txt`](raw_probe_stage_a.txt). The literal command
`snapshot_download(repo_id="atomscott/soccertrack-v2", repo_type="dataset",
allow_patterns=["README.md"])` was executed at 2026-08-25T02:07:22Z and
failed: **`ProxyError: 403 Forbidden`**. Sole-host check re-confirmed from
the toolkit clone: README/docs/scripts point exclusively to the HF dataset;
the GitHub repo carries no data (no LFS, no GT, no match video — its three
`docs/assets/demo-*.mp4` are 0.5–29 MB rendered visualization clips without
annotations, unusable for the frozen protocol).

## H. §§6–20 status — blocked stages and their ready-to-run instruments

Every blocked stage has a tested, frozen instrument waiting for data+GPU:

| § | Stage | Status | Instrument (tested in CI, 70/70) |
|---|---|---|---|
| 6 | v2 integrity audit | BLOCKED (no data) | `runners/audit_data.py` |
| 7 | v2 evaluator sanity A/B/C | BLOCKED (real-GT rehearsal passed 11/11 in Rev 1) | `runners/sanity_checks.py` |
| 8 | Dense windows frozen pre-prediction | BLOCKED (generation command frozen) | `runners/select_dense_windows.py` + manifest |
| 9 | Oracle O1–O3 with real crops | BLOCKED (O1 rehearsed on real GT: HOTA 0.948 purity) | `runners/run_oracle.py` |
| 10–11 | D-FINE + RT-DETRv2 fine-tune (TRAIN-only, VAL-tuned) | BLOCKED (GPU) | licenses verified Apache-2.0; recipe in README steps 8–9 |
| 12 | px-height↔recall | BLOCKED (needs detector output) | `runners/px_height_recall.py` |
| 13 | Real ReID (OSNet/torchreid) | BLOCKED (GPU+video) | `ml/reid/embedder.py` |
| 14 | VAL sweep incl. ambiguity margin 0 | BLOCKED | `run_oracle.py --ambiguity-margin` flags |
| 15 | Pipeline ladder P1–P4 + reconciliation accounting | BLOCKED | `runners/run_pipeline.py` |
| 16 | Full-half long-horizon | BLOCKED | `long_horizon_stats` in oracle/pipeline runners |
| 17 | Dense-window failure classification | BLOCKED | manifest + runners |
| 18 | Stride ablation | BLOCKED | `run_pipeline.py --strides` |
| 19 | GPU profiling (MEASURED rows) | BLOCKED | profiling protocol in README; CPU rows already MEASURED (923 fps tracking) |
| 20 | TEST scoring via frozen decision | BLOCKED | `runners/make_verdict.py` + frozen thresholds |

## I. Real evidence already banked (Revision 1, verified intact on this branch)

Sanity A/B/C: 11/11 on real GT incl. closed-form agreement (30% drop → IDF1
0.823 vs 0.8235 theory). O1 oracle on real GT: purity HOTA 0.948 / AssA
0.901 / 37 ambiguity terminations; continuity mode 1.000. CPU tracking
923 fps. Official match-disjoint split frozen verbatim. Dense-window
selector validated on real GT. Camsim `Dn` ranking. All under
`reports/gate0a/` on `main`, hashes unchanged by the merge.

## J. Why nothing was fabricated

The instructions bind a verdict to real TEST inference on real v2 data with
real models on a real GPU. None of those inputs exists in this environment;
`make_verdict` therefore refuses a verdict by construction (§R below) and
the only honest outputs are: fresh evidence, a new blocker, and a runnable
path to the real verdict. That is what this report is.

## K. The NEW blocker (official statement)

> **GATE 0A REVISION 2 NOT EXECUTABLE FROM THIS SESSION.** The Revision 2
> authorization names the owner's local machine as the execution
> workstation. This session verifiably executes in the account's only
> Claude Code environment (`env_01BWXwEeu7xncKhu95swQPwA`,
> `anthropic_cloud`): a 4-core Xeon cloud container with no NVIDIA silicon
> at the PCI level and an egress policy that answers 403 to CONNECT for
> `huggingface.co`/`cdn-lfs.huggingface.co` — the sole host of
> SoccerTrack v2 (live Stage A attempt failed `ProxyError: 403`). The
> account exposes no self-hosted or GPU environment; no local session or
> agent is reachable (`computer_unreachable` on the only local bridge);
> cloud purchases are prohibited. The local-machine authorization therefore
> has no executable channel from this session.

## L. How this differs from the Revision 1 blocker

Revision 1 said: *this container* lacks GPU and data egress; here is a
handoff. Revision 2 adds the decisive, newly verified facts: (1) the
session's placement — the owner's local machine is a **different computer**
this session cannot reach; (2) the account-level search — **no** self-hosted
environment, **no** reachable local session, bridge fails
`computer_unreachable`; (3) silicon-level hardware proof (PCI vendor scan)
replacing driver-level absence; (4) a live, verbatim Stage A failure and the
proxy gateway's own denial log. §2's "do not accept the old blocker" was
honored: everything was re-proven from scratch before being extended.

## M. Remedies (any one unblocks Revision 2B)

1. **Self-hosted environment on the local GPU machine** (faithful realization
   of the Revision 2 authorization): install the Claude Code self-hosted
   runner on that machine, register it as an environment; a session there
   executes the frozen runbook directly.
2. **Manual run of the frozen runbook on the local machine** — fastest, zero
   infrastructure: `git clone` → `ml/gate0a/README.md` steps 7–15 with
   `ml/gate0a/fetch_data.md` (exact commands; ~30–60 min attended, rest
   unattended) → commit `reports/gate0a/**` → this session assembles the
   machine verdict from the real artifacts.
3. **Policy + hardware change here**: allow `huggingface.co` +
   `cdn-lfs.huggingface.co` in this environment's network policy *and*
   provide a GPU environment.

## N. Revision 2B readiness

On unblock, execution resumes at §5 Stage A with zero rework: contract
hashes pinned, split frozen, dense-window generation command frozen,
runners tested (70/70), licenses verified, VAL-sweep and reconciliation
accounting flags already implemented. The one remediation iteration
permitted by §26 remains unspent.

## O. §21 autonomous error recovery log (this revision)

Errors encountered and handled without deviation: `torch` absent from
`.venv-ml` (expected — never required for CPU-valid stages; noted, not
"fixed" by pointless CPU install); `ffprobe` absent (demo-asset triage done
by size/name instead — the assets are irrelevant to the protocol either
way); `git lfs` absent (LFS question settled via `.gitattributes` absence).
No error required retrying the frozen protocol or altering any contract
file.

## P. §23 Phase 0b

**Not started**, in compliance: no platform migration, no backend/frontend
changes, no schema/queue work. The Revision 2 diff touches only
`reports/gate0a/revision2/`.

## Q. §24 camsim update

Requires the measured px-height↔recall curve from real detector output —
blocked with §12. The Revision 1 `Dn` ranking and its provisional
20 px floor stand unchanged; no fake "measured" update was written.

## R. §25 official verdict record

[`verdict.json`](verdict.json): `status: BLOCKED`, `verdict: null`,
thresholds sha256 pinned (`0d8bb0d6…`), six evidence artifacts listed. The
frozen decision function was **not** invoked with fabricated metrics.

## S. §26/§27 (remediation iteration / falsification report)

Not applicable — both trigger only on a CONDITIONAL PASS or FAIL from real
TEST metrics, which do not exist. Neither consumed.

## T. Artifact inventory (this revision)

```
reports/gate0a/revision2/
  executive_report.md            ← this file (§28 A–Z)
  verdict.json                   ← official machine record (§25): BLOCKED, new reason
  environment_verification.json  ← §2 machine-readable probe summary
  execution_surface_search.md    ← §22 exhaustive surface enumeration
  frozen_contract.json           ← §4 hash record + attestations
  raw_probe_hardware.txt         ← verbatim GPU/CPU/RAM/disk probes
  raw_probe_network.txt          ← verbatim egress probes + proxy status log
  raw_probe_stage_a.txt          ← verbatim §5 snapshot_download failure + sole-host check
  raw_frozen_contract_check.txt  ← verbatim sha256 run + data-in-clone check
  raw_demo_assets_check.txt      ← demo-asset triage record
```

## U. Reproducibility

Every claim above re-derives from the recorded commands: the probe blocks in
`raw_probe_*.txt` are copy-pasteable shell; the surface search names the
exact platform calls (`list_environments`, `ListAgents`, account session
list) and their dates; the verdict regenerates via
`python -m ml.gate0a.runners.make_verdict --blocked … --out …`. CI
(`scripts/ci_ml.sh`) passes on this branch — license gate, ruff, 70/70
tests, camsim smoke.

## V. Validity risks for this blocker

(1) *A GPU appears in this container class later* — re-probe before any 2B
resume (the §2 rule is now standing practice). (2) *The owner registers a
self-hosted environment after this report* — `list_environments` re-check is
step 0 of Revision 2B. (3) *HF policy change* — the Stage A command is the
canary; it either downloads or fails in seconds. None of these can silently
invalidate the report: each remedy path begins by re-running the exact probes
recorded here.

## W. Spend

No cloud resources, services, datasets, or APIs were purchased. Only free
egress to permitted hosts (pypi for `huggingface_hub`) was used.

## X. Compliance checklist vs the Revision 2 instructions

| § | Requirement | Status |
|---|---|---|
| 1 | Resume as Revision 2, real execution goal | honored; blocked at data/GPU with new evidence |
| 2 | Fresh re-verification, no reuse of old blocker | **done** (all probes re-executed 2026-08-25) |
| 3 | Git checkpoint: PR #2 green→ready→merge; `gate0a-revision-2` | **done** |
| 4 | Contract frozen; hashes recorded | **done** (byte-identical) |
| 5 | Progressive Stage A download | **attempted live; ProxyError 403** |
| 6–20 | Full real execution | blocked; instruments ready (§H) |
| 21 | Autonomous error recovery | exercised (§O) |
| 22 | Exhaustive surface search before any blocker; NEW blocker with hardware evidence | **done** (§D, §K) |
| 23 | No Phase 0b | honored |
| 24 | Camsim measured update | blocked with §12; nothing faked |
| 25 | Official machine verdict | BLOCKED record issued; no fabricated decision |
| 26–27 | Remediation / falsification | not triggered, not consumed |
| 28 | A–Z report + `reports/gate0a/revision2/` artifacts | this document |
| 29 | Real verdict **or** genuinely new verified blocker | the latter, delivered |

## Y. Owner handoff — the three buttons

- **Fastest (no infra):** on the local GPU machine run
  `git clone https://github.com/vansyson1308/aistockcounting && cd aistockcounting`
  then follow `ml/gate0a/README.md` steps 7–15 (data commands in
  `ml/gate0a/fetch_data.md`); commit the produced `reports/gate0a/**`.
- **Faithful to the Rev 2 authorization:** register the local machine as a
  Claude Code **self-hosted environment**, then start a session there on
  this repo and say "resume Gate 0A Revision 2B".
- **Cloud-side:** allow `huggingface.co` + `cdn-lfs.huggingface.co` in the
  environment network policy **and** attach a GPU environment, then say
  "resume Gate 0A Revision 2B" here.

## Z. Bottom line

The gate remains unjudged because judging it without real inference would be
a lie, and this environment — after fresh, silicon-level, policy-level, and
account-level verification — provably cannot produce real inference. The
protocol, thresholds, split, and tooling are frozen, tested, and waiting.
One of the three §Y actions converts this report into a real PASS /
CONDITIONAL PASS / FAIL, and §26's single remediation iteration is still
available for the CONDITIONAL case.
