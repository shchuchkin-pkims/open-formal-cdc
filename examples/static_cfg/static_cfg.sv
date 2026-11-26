// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Example: configuration register in domain A read by domain B without a synchronizer.
// This is safe only if the register is static during operation.
// BAD = 1: the design also updates the register by itself (hidden internal update).

module static_cfg #(parameter bit BAD = 0) (
  input  logic       clk_a, rst_a_n, wr,
  input  logic [3:0] wdata,
  input  logic       clk_b, rst_b_n,
  output logic [3:0] q_b
);
  logic [3:0] cfg;
  logic [2:0] cnt;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n) begin
      cfg <= 4'h5;
      cnt <= '0;
    end else begin
      cnt <= cnt + 1'b1;
      if (wr) cfg <= wdata;
      else if (BAD && cnt == 3'd7) cfg <= ~cfg;   // bug: internal update of a "static" register
    end
  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) q_b <= '0;
    else          q_b <= cfg;                     // no synchronizer: relies on cfg being static
endmodule
