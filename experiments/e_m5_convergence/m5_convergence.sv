// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Two source controls, independent 2FF chains and a reconverging AND.
// MODE 0: Gray sequence 00 -> 01 -> 11. MODE 1: paired transition 00 -> 11.
module m5_convergence #(parameter int MODE = 0) (
  input  logic clk_a,
  input  logic rst_a_n,
  input  logic inc,
  input  logic clk_b,
  input  logic rst_b_n,
  output logic joined
);
  logic src0, src1;
  logic meta0, meta1, q0, q1;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n) begin
      src0 <= 1'b0;
      src1 <= 1'b0;
    end else if (inc) begin
      if (MODE == 0) begin
        if (!src1 && !src0)
          src0 <= 1'b1;
        else if (!src1 && src0)
          src1 <= 1'b1;
      end else if (!src1 && !src0) begin
        src0 <= 1'b1;
        src1 <= 1'b1;
      end
    end
  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) begin
      meta0 <= 1'b0;
      meta1 <= 1'b0;
      q0 <= 1'b0;
      q1 <= 1'b0;
    end else begin
      meta0 <= src0;
      meta1 <= src1;
      q0 <= meta0;
      q1 <= meta1;
    end
  assign joined = q0 & q1;
endmodule
