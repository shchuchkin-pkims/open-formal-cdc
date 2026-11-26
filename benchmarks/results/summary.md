# Directed CDC benchmark results

Times are median wall-clock times of the recorded runs. Faults are scored by root cause.

| Case | Tool | Faults found | Time | Evidence |
|---|---|---:|---:|---|
| gray_sync/base | Open Formal CDC | 0/0 | 1.08 s |  |
| gray_sync/base | Jasper CDC | 0/0 | 4.88 s |  |
| gray_sync/binary | Open Formal CDC | 1/1 | 0.54 s | GRAY-BINARY [property]: gray_u_tx_ptr:cex |
| gray_sync/binary | Jasper CDC | 1/1 | 4.97 s | GRAY-BINARY [property]: CDC_u_sync.q_bus_gray_coded:cex |
| gray_sync/step2 | Open Formal CDC | 1/1 | 0.53 s | GRAY-STEP2 [property]: gray_u_tx_ptr:cex |
| gray_sync/step2 | Jasper CDC | 1/1 | 4.93 s | GRAY-STEP2 [property]: CDC_u_sync.q_bus_gray_coded:cex |
| handshake_mux/base | Open Formal CDC | 0/0 | 0.99 s |  |
| handshake_mux/base | Jasper CDC | 0/0 | 4.93 s |  |
| handshake_mux/data_changes | Open Formal CDC | 1/1 | 0.53 s | HS-DATA [property]: en_u_tx_data__u_rx_data_out:cex |
| handshake_mux/data_changes | Jasper CDC | 1/1 | 4.93 s | HS-DATA [property]: CDC_u_rx.data_out_datapath_stable:cex |
| async_fifo/base | Open Formal CDC | 0/0 | 18.52 s |  |
| async_fifo/base | Jasper CDC | 0/0 | 5.63 s |  |
| async_fifo/binary | Open Formal CDC | 1/1 | 11.32 s | FIFO-BINARY [property]: gray_wptr:cex, gray_rptr:cex |
| async_fifo/binary | Jasper CDC | 1/1 | 5.62 s | FIFO-BINARY [property]: CDC_u_wsync.q_bus_gray_coded:cex, CDC_u_rsync.q_bus_gray_coded:cex |
| async_fifo/overflow | Open Formal CDC | 1/1 | 0.71 s | FIFO-OVERFLOW [functional]: fifo:cex |
| async_fifo/overflow | Jasper CDC | 0/1 | 5.58 s | FIFO-OVERFLOW [functional]: not detected |
| async_fifo/read_reset | Open Formal CDC | 1/1 | 0.77 s | FIFO-RESET [functional]: fifo:cex, gray_rptr:cex |
| async_fifo/read_reset | Jasper CDC | 0/1 | 5.63 s | FIFO-RESET [functional]: not detected |
| pulse_sync/base | Open Formal CDC | 0/0 | 0.45 s |  |
| pulse_sync/base | Jasper CDC | 0/0 | 4.88 s |  |
| pulse_sync/short | Open Formal CDC | 1/1 | 0.50 s | PULSE-SHORT [property]: pulse_lvl__u_sync_s1:cex |
| pulse_sync/short | Jasper CDC | 1/1 | 4.88 s | PULSE-SHORT [property]: CDC_u_sync.q_data_stable:cex |
| glitch_conv/base | Open Formal CDC | 0/0 | 0.52 s |  |
| glitch_conv/base | Jasper CDC | 0/0 | 4.93 s |  |
| glitch_conv/binary | Open Formal CDC | 2/2 | 0.54 s | GLITCH-COMBO [sufficient_condition]: glitch_u_and_s1:cex<br>CONV-RECONVERGE [sufficient_condition]: conv_st_b:cex |
| glitch_conv/binary | Jasper CDC | 0/2 | 4.93 s | GLITCH-COMBO [sufficient_condition]: signature also fires on the known-good control<br>CONV-RECONVERGE [sufficient_condition]: not detected |
| glitch_conv/paired | Open Formal CDC | 1/1 | 0.48 s | CONV-PAIRED [sufficient_condition]: conv_st_b:cex |
| glitch_conv/paired | Jasper CDC | 0/1 | 4.93 s | CONV-PAIRED [sufficient_condition]: not detected |
| m5_heldout/base | Open Formal CDC | 0/0 | 0.69 s |  |
| m5_heldout/base | Jasper CDC | 0/0 | 5.02 s |  |
| m5_heldout/twin | Open Formal CDC | 1/1 | 0.84 s | M5-RECONVERGE-TWIN [functional]: m5_conv_joined:cex |
| m5_heldout/twin | Jasper CDC | 1/1 | 5.27 s | M5-RECONVERGE-TWIN [functional]: violation:reconvergence_check |
| m5_heldout/triple | Open Formal CDC | 1/1 | 1.21 s | M5-RECONVERGE-TRIPLE [functional]: m5_conv_joined:cex |
| m5_heldout/triple | Jasper CDC | 1/1 | 5.32 s | M5-RECONVERGE-TRIPLE [functional]: violation:reconvergence_check |
| static_cfg/base | Open Formal CDC | 0/0 | 0.31 s |  |
| static_cfg/base | Jasper CDC | 0/0 | 4.58 s |  |
| static_cfg/internal_update | Open Formal CDC | 1/1 | 0.48 s | STATIC-UPDATE [property]: cfg_static:cex |
| static_cfg/internal_update | Jasper CDC | 1/1 | 4.88 s | STATIC-UPDATE [property]: cfg_cdc_static:cex |

## Summary by design

| Design | Open Formal CDC | Jasper CDC |
|---|---:|---:|
| gray_sync | 2/2, 2.14 s | 2/2, 14.78 s |
| handshake_mux | 1/1, 1.52 s | 1/1, 9.86 s |
| async_fifo | 3/3, 31.33 s | 1/3, 22.47 s |
| pulse_sync | 1/1, 0.95 s | 1/1, 9.76 s |
| glitch_conv | 3/3, 1.54 s | 0/3, 14.78 s |
| m5_heldout | 2/2, 2.74 s | 2/2, 15.62 s |
| static_cfg | 1/1, 0.79 s | 1/1, 9.46 s |

## Overall

| Tool | Faults found | Total case time | Unscored |
|---|---:|---:|---:|
| Open Formal CDC | 13/13 | 41.01 s | 0 |
| Jasper CDC | 8/13 | 96.73 s | 0 |

## M4 ablation (Open Formal CDC)

`onechange` is a sufficient-condition heuristic. `nohazard` checks the RTL function-hazard model; its counterexample is not a proof of a physical glitch. Commercial evidence is shown in the tools' native semantics and is not equivalent to an M4 verdict.

| Case | onechange | nohazard (M4) | Reading | Jasper data_stable |
|---|---|---|---|---|
| glitch_conv/base | proven | cex | hazard_candidate | CDC_u_and.q_data_stable:cex |
| glitch_conv/binary | cex | cex | hazard_candidate | CDC_u_and.q_data_stable:cex |
| glitch_conv/paired | cex | proven | discharged | CDC_u_and.q_data_stable:cex |
