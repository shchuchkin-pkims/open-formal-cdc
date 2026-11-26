# Large CDC Benchmark Comparison

This suite compares the automatic CDC flows of Open Formal CDC and Cadence Jasper CDC on larger designs.

Current single-run results: [results/summary.md](results/summary.md).

## Cases

- `cdc_array`: 4, 16, and 64 channels, plus binary-bus and missing-stage mutations;
- `riscv_dmi`: RISC-V JTAG debug transport with a dual-clock DMI bridge;
- `axi_spi`: AXI SPI slave with two dual-clock FIFOs.

The real-IP cases currently measure analysis coverage and runtime. They do not have a reviewed fault ledger, so their messages are not presented as confirmed design bugs. The two synthetic mutations have known detection targets. A signature must be absent from the known-good base variant. In particular, Jasper reports Gray counterexamples on the base array because independent channels are combined into one destination bus; the binary mutation is not scored as detected by the same signature.

## Execution conditions

- Jasper CDC 2019.06p001;
- the same pinned RTL sources and generated synthetic variants for both tools;
- sequential runs on the same 16-core host;
- Jasper: 30 s per property and 2 min per proof phase, with 500 reset-analysis iterations; AXI SPI omits conditional-waiver proofs because Hp, Ht, and B all reject its negedge-fast-clock configuration with ECK112;
- commercial outer timeout: 600 s per case by default;
- Open Formal CDC: per-job timeout from the case YAML, with up to 8 parallel SBY jobs;
- no hand-written design-specific SVA for the commercial tools.

The scripts record tool status, source hash, runtime, property/check statuses, and normalized report findings.

## Run

```bash
# Open-source flow only
.venv/bin/python benchmarks/large/run.py --tools ofcdc

# Optional licensed tools
.venv/bin/python benchmarks/large/run.py --tools jasper

# Select a case or repeat in fresh directories
.venv/bin/python benchmarks/large/run.py --case cdc_array/base --tools ofcdc,jasper
.venv/bin/python benchmarks/large/run.py --repeat 3

# Run the same open-source cases with rIC3 instead of the default PDR engine
OFCDC_PROVE_ENGINE="aiger rIC3" .venv/bin/python benchmarks/large/run.py --tools ofcdc

# Limit the number of concurrent OFCDC jobs; the value is recorded in each result JSON
.venv/bin/python benchmarks/large/run.py --tools ofcdc --parallel 4

# Generate the report
.venv/bin/python benchmarks/large/report.py
```

Results are written to `results/summary.md` and per-case JSON files. Build products and commercial project databases are ignored.

The current suite takes 217.74 s in total for Open Formal CDC. The rIC3 proof engine reduced AXI SPI unknown checks from two to one. The five former RISC-V DMI unknown checks were cover-search timeouts, not failed proofs: `smtbmc boolector` with `cover_depth: 100` reached data-change at step 60 and capture at step 63 on the full model. All five checks are now proven, and the DMI case takes 42.86 s. This is evidence for a portfolio of engines, not for a universal speed or coverage advantage of one engine.

For the remaining AXI SPI check, an isolated CEGAR run confirmed a counterexample on the full model in 63 s. The standard large run with eight parallel jobs timed out at 120 s, while the same runner with `--parallel 4` produced counterexamples for all 18 checks in 151.66 s. Their wrapper and proof section are identical, so this is not a model mismatch. The parallel-8 JSON is retained as `results/axi_spi__base/ofcdc_parallel8.json`, and the current summary records `job_parallel=4`. Reducing concurrency eliminated the remaining unknown without changing the property or model.

## M5 evaluation, 25.11.2026

The optional `options.m5_checks: true` flow was also evaluated on the public large suite and on two held-out `cdc-rdc-tests` cases. These are single runs, not new medians, and they do not change the comparison tables above.

| Case | M5 result | Time and conditions |
|---|---|---|
| `cdc_array/small` | 8/8 `settled` proven; `m5_conv_data_b` cex; no invalid `m5_conv_flag_b` | 62.44 s including the ordinary checks; the previous ordinary run took 1.06 s |
| `cdc_array/base` | 32/32 `settled` proven; `m5_conv_data_b` cex; no invalid `m5_conv_flag_b` | 50.55 s including the ordinary checks; the previous ordinary run took 3.41 s |
| RISC-V DMI | 12/12 attributed packed-chain M5 checks proven, including four three-stage chains | 139.57 s including the ordinary checks, with `cover_depth: 300` and Boolector |
| AXI SPI | 4/4 M5 checks proven | 76.93 s for the four M5-only jobs with `cover_depth: 300` and Boolector |
| CDC-014 clean chain | `m5_sync_2` proven | 30.80 s in ticks |
| CDC-014 AND between stages | `m5_sync_2` proven | 20.57 s in ticks |

For AXI SPI, the initial depth-40 run left two checks `unknown` only in their cover tasks. Depth 100 closed one of them; the remaining `rx.din_full` case reached its first injection at step 107 and its pending/second injections at step 111. The final four-job run used depth 300. This is evidence for per-case cover limits, not for increasing every timeout by default.

The optional `m5_group` mode was measured separately. On `cdc_array/small`, eight independent M5 jobs took 28.00 s, while one grouped job with the same eight independent properties and covers took 45.10 s. Grouping reuses the first M2a but makes the solver problem harder, so it is disabled by default and is not presented as a speed optimization. With rIC3 instead of ABC PDR, the same grouped job took 27.40 s; PDR with Boolector took 30.40 s. All three variants were proven with all covers. These alternatives can be selected per M5 job with `m5_prove_engine`, `m5_cover_engine`, and `m5_cover_depth`, without changing other CDC checks.

Additional held-out `cdc-rdc-tests` runs checked shared-source fanout and reconvergence. CDC-005 twin and triple chains produced `m5_conv` counterexamples, while CDC-005 single and CDC-024 without reconvergence produced only proven `settled` checks. Their times were 21.59, 32.68, 34.85, and 20.34 s respectively. The independent `experiments/e_m5_heldout` regression reproduces twin and triple cases in both time models with all M5 covers.

The permanent smaller regression is `tests/flow/test_m5_large.py`. M5 is available inside synchronizer modules declared in the `cells` section, with full internal results under `cells.<module>` in `results.json`. It is not generated for `mux_enable` captures. Attributed vector flops are supported for packed chains satisfying `D[kW+i] == Q[(k-1)W+i]`. M5 is inserted on the first two stages and `remaining_d` preserves later stages. Other `cdc_sync` structures are not unfolded automatically.
