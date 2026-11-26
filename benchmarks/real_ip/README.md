# Real-IP CDC Benchmarks

These configurations run Open Formal CDC on public production RTL without copying the external sources into this repository. `fetch.py` downloads five pinned repositories into the ignored `benchmarks/cache/` directory.

## Available designs

| Design | Top | Main CDC structures | Cells | Flip-flop bits | Crossings |
|---|---|---|---:|---:|---:|
| RISC-V JTAG debug transport | `dmi_jtag` | Bidirectional two-phase DMI bridges, synchronizer cells, clear/reset sequencing | 1142 | 416 | 49 |
| AXI SPI slave | `axi_spi_slave` | Two token-ring dual-clock FIFOs, input synchronizers, AXI/SPI data transfers | 896 | 957 | 36 |

The measurements above come from the flattened Yosys netlists at the pinned revisions. They qualify the designs for structural and performance experiments. They are not yet scored bug-detection results: reported `none`, convergence, and reset findings require design-specific review before entering the fault ledger. In particular, the SPI FIFO uses token-ring pointers, so a generic Gray-code counterexample is a template mismatch, not evidence of an SPI bug.

## Sources and licenses

| Repository | Pinned revision | License |
|---|---|---|
| `pulp-platform/riscv-dbg` | `643607e19df3435cfd77cc56143e2637f5900a6e` | SHL-0.51, with an Apache-2.0 option |
| `pulp-platform/axi_spi_slave` | `b15bdd4126610e8ef01f3a3722be791f4dde9d4e` | SHL-0.51, with an Apache-2.0 option |
| `pulp-platform/common_cells` | `b5ec8905ed7828655155b0ae971023adf793c600` | SHL-0.51, with an Apache-2.0 option |
| `pulp-platform/tech_cells_generic` | `55cb54513e2d426be5992d311cb9d5dbcad10c78` | SHL-0.51, with an Apache-2.0 option |
| `pulp-platform/axi_slice_dc` | `fbfb22bd5ce999e74f2f97440df77c435bf22883` | SHL-0.51, with an Apache-2.0 option |

The RISC-V filelist defines `VERILATOR` to exclude upstream parallel SVA that yosys-slang does not support. This does not change the RTL sources. The AXI SPI configuration uses `clk2fflogic`, because its TX clock mux creates a derived clock that the tick-based model does not support.

## Run

```bash
python3 benchmarks/real_ip/fetch.py
python3 benchmarks/real_ip/fetch.py --check

.venv/bin/open-formal-cdc analyze benchmarks/real_ip/riscv_dmi/ofcdc.yaml
.venv/bin/open-formal-cdc analyze benchmarks/real_ip/axi_spi/ofcdc.yaml
```

Use `run` instead of `analyze` to generate and execute formal checks. Start with a single check through `--check <name>` when bringing up a new environment. The RISC-V DMI configuration uses rIC3 for proofs and Boolector with cover depth 100: the default Yices search timed out before the JTAG capture sequence, while Boolector reached both covers at steps 60 and 63 on the full model. The AXI SPI configuration selects rIC3 explicitly for proofs. An isolated CEGAR run found a full-model counterexample for `data[127:96]` in 63 s. Eight parallel large-suite jobs timed out, but `--parallel 4` produced all 18 counterexamples in 151.66 s with the same wrapper and proof configuration. The current large-suite therefore reports `cex=18` and records `job_parallel=4`; the parallel-8 JSON is retained separately. Commercial-tool results are not included yet.
