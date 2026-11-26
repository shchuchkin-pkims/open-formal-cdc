// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Monotonic source and a two-flop receiver used to calibrate M2a and M5 latency.
module sync_chain (
  input  logic clk_a,
  input  logic rst_a_n,
  input  logic set_a,
  input  logic clk_b,
  input  logic rst_b_n,
  output logic sync_q
);
  logic src_q;
  logic meta_q;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n)
      src_q <= 1'b0;
    else if (set_a)
      src_q <= 1'b1;
  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) begin
      meta_q <= 1'b0;
      sync_q <= 1'b0;
    end else begin
      meta_q <= src_q;
      sync_q <= meta_q;
    end
endmodule
