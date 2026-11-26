// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Abstraction refinement example. In the good design cap is low whenever data_q
// changes. Abstracting dst_data_q breaks that relation and creates a spurious
// data-stability counterexample. BAD=1 makes the counterexample real.
module cegar #(parameter int BAD = 0) (
  input  logic clk_a,
  input  logic rst_a_n,
  input  logic clk_b,
  input  logic rst_b_n,
  input  logic data_in,
  output logic out_q
);
  logic data_q, dst_data_q, cap;
  assign cap = (BAD != 0) ? dst_data_q : (data_q & dst_data_q);

  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n) data_q <= 1'b0;
    else          data_q <= data_in;

  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) begin
      dst_data_q <= 1'b0;
      out_q      <= 1'b0;
    end else begin
      dst_data_q <= data_q;
      if (cap) out_q <= data_q;
    end
endmodule
