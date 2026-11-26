# CDC Verification Benchmarks

This directory contains a reproducible directed benchmark for Open Formal CDC and Cadence Jasper CDC, plus a plan for larger public RTL suites.

The goal is to measure **which independent design faults are found**, with which false-positive cost, and at what runtime. Raw violation counts and generated-property counts are not comparable across tools and are not used as the primary score.

Current tables: [directed suite](results/summary.md), [large synthetic and real-IP suite](large/results/summary.md).

## 1. Test-suite structure

The suite has three levels.

| Level | Source | Purpose | Status |
|---|---|---|---|
| Directed examples | `examples/` in this repository | Known-good and faulty variants of every implemented property template; both formal time models | Available |
| Public rule suites | `adibis/cdc-rdc-tests`, `rtl-buddy-cdc`, `clockguard` | Broad structural/rule coverage and regression against fixed expected answers | First suite available; others planned |
| Real multi-clock IP | Peripheral, debug, SoC, and library-cell designs | Realistic reconvergence, FIFO, reset, and metastability behavior at larger scale | SPI and RISC-V debug available for structural analysis; scored faults planned |

### Directed examples

The existing examples already provide the mutation-test foundation:

- `gray_sync`: Gray bus, binary bus, and a two-bit source transition;
- `handshake_mux`: stable transfer and data changing during capture;
- `async_fifo`: correct FIFO, overflow, binary pointers, and independent resets;
- `pulse_sync`: pulse-width and clock-ratio cases;
- `glitch_conv`: combinational glitch and reconvergence cases;
- `static_cfg`: valid and invalid static-signal assumptions.

Each template must have at least one known-good and one faulty variant. A proof on the good variant and a counterexample on the faulty variant are both required.

The [synthetic `cdc_array`](synthetic/) adds a scalable 4/16/64-channel design. Its 64-channel variant has 2176 flip-flop bits and 128 crossings; binary and missing-stage mutations provide known negative controls. The targeted formal run passed all 5 expected outcomes.

The [real-IP configurations](real_ip/) provide pinned RISC-V JTAG and AXI SPI designs with 416 and 957 flip-flop bits, respectively.

### Public rule suites

External suites are fetched at a pinned commit; their sources are not copied into this repository unless their license explicitly permits it.

| Suite | License | Size | Current use |
|---|---|---:|---|
| `adibis/cdc-rdc-tests` | Apache-2.0 | 213 directed cases | Structural and selected formal checks; see [docs/validation.md](../docs/validation.md) |
| `rtl-buddy-cdc` | BSD-3-Clause | 226 good/bad pairs | Planned |
| `clockguard` | MIT | 27 small projects | Planned |

### Real IP selection

A real design is admitted only if it has genuine asynchronous behavior. A large RTL repository with one clock is not a useful CDC benchmark.

| Candidate class | Required clock/reset structure | Faults to preserve or inject |
|---|---|---|
| SPI controller | Host clock and independently driven serial clock | Missing input synchronization, pulse loss, unstable multi-bit status/data transfer |
| RISC-V debug subsystem or SoC | JTAG TCK, debug-module clock, core/system clock | Broken request/acknowledge pairing, reset-domain capture, event loss |
| Async FIFO and CDC cell library | Independent read/write clocks and resets | Binary instead of Gray pointers, missing stage, reset of only one side, data-order corruption |
| OpenTitan/PULP-based blocks | Real synchronizer cells, peripheral crossings, reset synchronizers | Historical bugs where available, plus reviewed mutations |
| Larger SoC subsystem | At least two asynchronous core/peripheral/debug domains | Reconvergence, quasi-static configuration, FIFO and handshake interactions |

Every real design needs:

1. A pinned upstream revision and a redistributable license.
2. A documented known-good configuration.
3. At least one confirmed historical bug or a small, reviewed mutation.
4. A complete clock/reset/input-domain description.
5. A top level and parameter set that all participating tools can elaborate.

A RISC-V core without a separate debug, peripheral, or other asynchronous domain is excluded. Complex designs should enter the suite only after their clock/reset constraints have been reviewed.

## 2. Fault ledger

Each design has a machine-readable fault ledger. Each entry represents one independent root cause, not one tool message.

Required fields:

- `id`: stable identifier such as `SPI-01`;
- `class`: `unsync`, `chain`, `gray`, `handshake`, `pulse`, `glitch`, `reconvergence`, `fifo`, `rdc`, `metastability`, or `clock_mux`;
- `variant`: parameter set or mutation that activates the fault;
- `location`: source file and symbol or line range;
- `description`: expected failure mechanism;
- `detection_level`: `structural`, `formal`, `metastability`, or a combination;
- `claim`: `property`, `sufficient_condition`, or `functional`;
- `source`: historical bug, manual review, or mutation;
- `known_good`: variant in which this fault is absent.

Mutations are stored separately from upstream RTL and must be reviewed against the corresponding known-good variant. Multiple mutations in one run are allowed only for scalability tests, not for fault-detection scoring.

Claims distinguish the strength of the evidence. `property` is a violation of a formal property, not necessarily a functional failure. `sufficient_condition` is a heuristic warning such as `onechange`; it does not prove a function hazard or a physical glitch. `functional` is a counterexample to incorrect design behavior under the stated model and environment. None of these labels alone is a proof of a silicon failure.

For glitch cases, the report also includes an M4 ablation table: `agree_safe` (both checks prove safety), `discharged` (`onechange` fails but M4 proves no function hazard), `hazard_candidate` (both produce counterexamples), and `unresolved`. The M4 result is independent of the fault score. Native Jasper `data_stable` evidence is shown for context; this check has different semantics and is not treated as an M4-equivalent proof or automatically counted as a false positive.

## 3. Fair execution protocol

For every tool and design:

1. Use the same RTL revision, top module, parameters, clock/reset relations, input-domain constraints, and reviewed waivers.
2. Keep tool-specific setup in separate runner scripts, but make its semantics equivalent.
3. Record tool version, OS, CPU, RAM, thread count, command line, configuration hash, and cache state.
4. Use the same per-property/per-check and total timeouts. Report a timeout as unresolved, never as a proof or a detected fault.
5. Measure front-end/structural analysis and formal proof separately, then report total wall-clock time.
6. Run each configuration three times after a documented cold run and report the median. Keep all raw logs.
7. Run known-good and faulty variants independently.
8. Review counterexamples against the environment before classifying them as design faults.

Open Formal CDC runs locally with open-source tools. The Jasper runner is optional and requires an existing installation. No commercial run is part of the default test command.

## 4. Scoring rules

A fault is **detected** when at least one non-waived finding maps to its fault-ledger ID. Several messages caused by the same root cause count once. For mutation cases, the mapped signature must also be absent from the known-good control; a warning or counterexample present in both variants does not detect the mutation.

| Metric | Definition |
|---|---|
| Detected faults | Number of fault-ledger IDs with a confirmed finding |
| Missed faults | Known faults with no corresponding finding |
| Additional findings | Findings not yet mapped to a ledger ID; subdivide after review into confirmed new bugs or false positives |
| False positives | Reviewed findings whose reported failure is impossible under the agreed constraints |
| Environment counterexamples | Counterexamples caused by missing or incorrect environment assumptions; reported separately |
| Unresolved | Checks that timed out, were unsupported, or ended without a definite result |
| Runtime | Median wall-clock time under the common protocol; unavailable runs are excluded from totals |

Precision and recall are calculated only after manual adjudication. A high number of violations is not automatically a better result.

## 5. Result format

Store one JSON result per design, variant, and tool. Include the design revision, tool version, execution metadata, per-fault mapping, counts, and timing. Generate Markdown tables from those JSON files rather than editing scores manually.

The comparison table for each design has this form:

| Design | Tool | Faults found | False positives | Unresolved | Structural time | Formal time | Total time |
|---|---|---:|---:|---:|---:|---:|---:|
| Example design | Open Formal CDC | - | - | - | - | - | - |
| Example design | Jasper CDC | - | - | - | - | - | - |

`Faults found` is shown as `detected/known`. Missing commercial results remain `Not run`; no value is inferred from another tool.

### Directed suite result

The completed v2 run contains 114 successful process executions: 19 variants, 2 tools, and 3 fresh-directory repetitions. Verdicts and M4 ablation readings were stable across repetitions.

| Tool | Faults found | Total median case time |
|---|---:|---:|
| Open Formal CDC 0.0.1 | 13/13 | 41.01 s |
| Jasper CDC 2019.06p001 | 8/13 | 96.73 s |

The total is the sum of per-case median times, including known-good controls. It is not the elapsed time of a parallel suite run. Per-design and per-case tables, including evidence for every score, are in [results/summary.md](results/summary.md).

The M4 ablation has three stable outcomes: `hazard_candidate` for both Gray and binary, and `discharged` for paired `00 <-> 11`. In the paired case, `onechange` produces a counterexample while M4 proves that the AND cone has no function hazard. The Gray result is a function-hazard candidate under free clock relations, not a claim that Gray encoding itself is broken. Native Jasper findings are reported separately and are not treated as M4-equivalent proofs.

### Public rule-suite reference result

For `adibis/cdc-rdc-tests` at commit `737825c0`, the documented Open Formal CDC run reports:

| Scope | Expected findings detected | Additional findings | Exact cases | Runtime |
|---|---:|---:|---:|---:|
| 8 supported rules | 45/47 | 3 | 209/213 | 41 s |

The four non-exact cases and all rule mappings are documented in [docs/validation.md](../docs/validation.md). This is a rule-suite result, not a real-IP fault score.

## 6. Scope and review notes

The directed comparison measures the tools' automatic CDC flows. No hand-written, design-specific SVA is supplied to Jasper. A miss therefore means that the configured automatic CDC flow did not distinguish the fault; it does not prove that a custom formal testbench cannot detect it.

Additional reports on known-good controls are retained in normalized JSON but are not silently called false positives. In particular, generic data-stability counterexamples under free clocks and structural RDC messages need separate environment and reset analysis. They do not increase the score for a targeted mutation.

The `async_fifo/read_reset` variant changes the reset mode, not the RTL. The current commercial runners use their standard reset declarations and produce no fault-specific Gray/data-order signature. The miss is reported for this configuration; it is not a claim about every possible commercial reset-modeling setup.

## 7. Running the directed benchmark

The suite manifest is `suite.json`. It defines 19 variants: 7 known-good controls and 12 faulty variants containing 13 independent faults, including shared-source M5 reconvergence. Both tools read the same generated RTL copy for each variant. The `glitch_conv/paired` case checks the M4 ablation directly: `00 <-> 11` violates `onechange`, while the AND cone has no function hazard; its independently synchronized outputs still present a reconvergence risk.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
export PATH="/path/to/oss-cad-suite/bin:$PATH"

# Open-source flow
.venv/bin/python benchmarks/run.py --tools ofcdc

# Optional licensed tools on the configured benchmark host
.venv/bin/python benchmarks/run.py --tools jasper

# Generate normalized JSON and Markdown summaries
.venv/bin/python benchmarks/score.py
```

Use `--case gray_sync/binary` to select one case and `--repeat 3` for three fresh-directory runs with median timing. The commercial module and version are explicit in `run.py`; adapt the module name when running on another installation.

## 8. Repository layout

```text
benchmarks/
  README.md                 # methodology and reproduction commands
  suite.json                # case matrix, fault ledger, and tool-specific evidence rules
  run.py                    # RTL preparation, tool launchers, and report parsers
  score.py                  # fault scoring and generated Markdown tables
  results/                  # normalized JSON and generated summaries
  real_ip/                  # pinned RISC-V and AXI SPI configurations and fetcher
  synthetic/                # scalable CDC array with known-good and faulty variants
  large/                    # cross-tool large-design runner and results
  build/                    # generated RTL, logs, projects, and traces; not committed
  suites/                   # future public-suite manifests
  designs/                  # future real-IP configurations
  mutations/                # future reviewed real-IP mutations
```

Implementation order: directed examples, public rule suites, CDC cells/FIFO, SPI, RISC-V debug/SoC, then larger SoC designs. This keeps the ground truth understandable before runtime and scalability become the main challenge.
