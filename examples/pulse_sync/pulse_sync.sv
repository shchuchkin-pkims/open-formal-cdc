// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Example: level crossing fast (a) to slow (b) through a 2FF synchronizer.
// The source holds every new value for at least HOLD cycles of clk_a.
// With clk_a = 4 ns and clk_b = 10 ns, HOLD = 8 (32 ns) is always seen by clk_b;
// HOLD = 1 (4 ns) can be lost between two edges of clk_b.

module sync2 (input logic clk, rst_n, d, output logic q);
  logic s1;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin s1 <= 1'b0; q <= 1'b0; end
    else begin s1 <= d; q <= s1; end
endmodule

module pulse_sync #(parameter int HOLD = 8) (
  input  logic clk_a, rst_a_n, stim,
  input  logic clk_b, rst_b_n,
  output logic q_b
);
  logic       lvl;
  logic [3:0] cnt;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n) begin
      lvl <= 1'b0;
      cnt <= '0;
    end else if (cnt != 0) begin
      cnt <= cnt - 1'b1;
    end else if (stim != lvl) begin
      lvl <= stim;
      cnt <= 4'(HOLD - 1);
    end
  sync2 u_sync (.clk(clk_b), .rst_n(rst_b_n), .d(lvl), .q(q_b));
endmodule
