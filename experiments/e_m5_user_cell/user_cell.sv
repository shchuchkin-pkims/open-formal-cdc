// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// A declared synchronizer cell whose internal second stage is checked with M5.
module sync2 (
  input  logic clk,
  input  logic rst_n,
  input  logic d,
  output logic q
);
  logic meta_q;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin
      meta_q <= 1'b0;
      q <= 1'b0;
    end else begin
      meta_q <= d;
      q <= meta_q;
    end
endmodule

module user_cell_top (
  input  logic clk_a,
  input  logic rst_a_n,
  input  logic set_a,
  input  logic clk_b,
  input  logic rst_b_n,
  output logic q_b
);
  logic src_q;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n)
      src_q <= 1'b0;
    else if (set_a)
      src_q <= 1'b1;
  sync2 u_sync (.clk(clk_b), .rst_n(rst_b_n), .d(src_q), .q(q_b));
endmodule
