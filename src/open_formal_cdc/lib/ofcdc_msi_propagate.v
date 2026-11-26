// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// M5 same-domain metastability propagation. A trigger on the first stage leaves
// a pending event. On the first later receiver edge where D changes, the next
// flop may capture either the previous or current D independently for each bit.
module ofcdc_msi_propagate #(parameter W = 1, parameter TICKS = 0) (
  input          cap,
  input          act,
  input  [W-1:0] trigger,
  input  [W-1:0] d,
  output [W-1:0] d_seen,
  output         msi_alt
);
  reg [W-1:0] d_prev, d_older;
  reg         valid = 1'b0;
  reg [W-1:0] changed_q = {W{1'b0}};
  reg [W-1:0] pending = {W{1'b0}};
  wire [W-1:0] changed = {W{valid}} & (d ^ d_prev);
  wire [W-1:0] window = TICKS ? changed : changed_q;
  wire [W-1:0] propagate = {W{act}} & window & (pending | trigger);
  always @($global_clock)
    if (cap) begin
      d_older  <= d_prev;
      d_prev   <= d;
      valid    <= 1'b1;
      changed_q <= changed;
      if (!act)
        pending <= {W{1'b0}};
      else
        pending <= (pending | trigger) & ~propagate;
    end
  wire [W-1:0] d_old = (TICKS || !valid) ? d_prev : d_older;
  wire [W-1:0] pick = $anyseq;
  wire [W-1:0] old_pick = propagate & pick;
  assign d_seen = (old_pick & d_old) | (~old_pick & d);
  assign msi_alt = |(d_seen ^ d);
endmodule
