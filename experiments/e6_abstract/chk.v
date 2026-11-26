// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Global-step check: output x changes only in the step of a clk_a edge.
module chk (input clk_a, input en);
  wire x;
  flop u (.clk_a(clk_a), .en(en), .x(x));
  reg x_q, c_q, started = 1'b0;
  always @($global_clock) begin x_q <= x; c_q <= clk_a; started <= 1'b1; end
  always @(*) if (started && x != x_q) p_edge_only: assert (clk_a && !c_q);
  always @(*) if (started) c_toggle: cover (x != x_q);
endmodule
