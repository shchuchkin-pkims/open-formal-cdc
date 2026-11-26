# Large CDC benchmark results

Real-IP cases have no reviewed fault ledger and are reported by analysis counts, not confirmed bugs.
Synthetic fault scores use the known binary and missing-stage mutations.

| Case | Tool | Known faults found | Checks / properties | Violations / verdicts | Jobs | Time |
|---|---|---:|---|---|---:|---:|
| cdc_array/small | Open Formal CDC | n/a | cex=1, proven=8 | unresolved=8 | n/a | 1.06 s |
| cdc_array/small | Jasper CDC | n/a | cex=4 | bus_gray_coded=2, cdc_pair_logic=1, data_stable=2 | n/a | 4.97 s |
| cdc_array/base | Open Formal CDC | n/a | cex=1, proven=32 | unresolved=32 | n/a | 3.41 s |
| cdc_array/base | Jasper CDC | n/a | cex=4 | bus_gray_coded=2, cdc_pair_logic=1, data_stable=2 | n/a | 5.03 s |
| cdc_array/large | Open Formal CDC | n/a | cex=1, proven=128 | unresolved=128 | n/a | 13.99 s |
| cdc_array/large | Jasper CDC | n/a | cex=4 | bus_gray_coded=2, cdc_pair_logic=1, data_stable=2 | n/a | 5.38 s |
| cdc_array/binary | Open Formal CDC | 1/1 | cex=33 | unsafe=32 | n/a | 2.92 s |
| cdc_array/binary | Jasper CDC | 0/1 (base also cex) | cex=4 | bus_gray_coded=2, cdc_pair_logic=1, data_stable=2 | n/a | 4.93 s |
| cdc_array/missing_stage | Open Formal CDC | 1/1 | cex=1, proven=16 | no_scheme=16, unresolved=16 | n/a | 1.85 s |
| cdc_array/missing_stage | Jasper CDC | 0/1 | cex=2, proven=2 | bus_gray_coded=1, cdc_pair_fanout=1, cdc_pair_logic=1, data_stable=1 | n/a | 8.48 s |
| riscv_dmi/base | Open Formal CDC | n/a | proven=5 | no_scheme=32, safe=5, structural=12 | n/a | 42.86 s |
| riscv_dmi/base | Jasper CDC | n/a | cex=11, proven=10, undetermined=43, unprocessed=44 | cdc_pair_fanout=4, cdc_pair_logic=34, convergence_check=45, glitch_check=3, no_scheme=34, sync_chain_fanout=3, sync_chain_logic=4, unclocked_signal=2 | n/a | 244.90 s |
| axi_spi/base | Open Formal CDC | n/a | cex=18 | no_scheme=11, unresolved=2, unsafe=23 | 4 | 151.66 s |
| axi_spi/base | Jasper CDC (no waiver proof) | n/a | cex=3, undetermined=8, unprocessed=20 | bus_gray_coded=2, cdc_pair_fanout=2, cdc_pair_logic=2, convergence_check=13, data_stable=1, glitch_check=3, no_scheme=2, reconvergence_check=2, sync_chain_fanout=1, sync_chain_logic=1 | n/a | 125.02 s |

Total case time is the sum of per-case wall-clock times.

## Aggregate runtime

| Tool | Runs | Errors/timeouts | Total case time |
|---|---:|---:|---:|
| Open Formal CDC | 7 | 0 | 217.74 s |
| Jasper CDC | 7 | 0 | 398.71 s |
