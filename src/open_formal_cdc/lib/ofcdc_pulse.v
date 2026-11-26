// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-PULSE: every value of the source is held for at least N edges of the destination
// clock, so a synchronizer cannot miss it (N = 2 leaves room for a metastable first
// sample). Runs on the global step and counts destination edges that sample the
// current source value.
// TICKS = 1: a flop samples the value of the step of its edge (tick model).
// TICKS = 0: a flop samples the value of the previous step (clk2fflogic), so an edge
//            in the step where the source changes still samples the old value.
module ofcdc_pulse #(parameter W = 1, parameter N = 2, parameter TICKS = 1) (
  input         act,      // both domains out of reset
  input         edge_d,   // destination clock edge in this step
  input [W-1:0] src
);
  reg [W-1:0] prev;
  reg [3:0]   held = 4'd0;   // destination edges that sampled the current value
  reg         started = 1'b0;
  reg         first_done = 1'b0;  // the value held since reset is not a pulse
  always @($global_clock) begin
    prev    <= src;
    started <= act;
    if (!act) first_done <= 1'b0;
    else if (changed) first_done <= 1'b1;
  end
  wire       changed  = started && act && (src != prev);
  // samples of the value that ends in this step
  wire [4:0] held_old = TICKS ? {1'b0, held} : {1'b0, held} + edge_d;
  always @($global_clock)
    if (!act)         held <= 4'd0;
    else if (changed) held <= (TICKS && edge_d) ? 4'd1 : 4'd0;
    else if (edge_d && held != 4'hf) held <= held + 1'b1;
  always @(*)
    if (changed && first_done) begin
      p_pulse: assert (held_old >= N);
      c_change: cover (1'b1);
    end
endmodule
