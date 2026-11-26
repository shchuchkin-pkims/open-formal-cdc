// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Two same-domain receivers after one first stage, with optional logic on one branch.
module fanout_m5 #(parameter int LOGIC = 0) (
  input  logic clk_a,
  input  logic rst_a_n,
  input  logic set_a,
  input  logic clk_b,
  input  logic rst_b_n,
  input  logic pass_b,
  output logic q0,
  output logic q1
);
  logic src_q;
  logic meta_q;
  wire second_d1 = (LOGIC != 0) ? (meta_q & pass_b) : meta_q;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n)
      src_q <= 1'b0;
    else if (set_a)
      src_q <= 1'b1;
  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) begin
      meta_q <= 1'b0;
      q0 <= 1'b0;
      q1 <= 1'b0;
    end else begin
      meta_q <= src_q;
      q0 <= meta_q;
      q1 <= second_d1;
    end
endmodule
