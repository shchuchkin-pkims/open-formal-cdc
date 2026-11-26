// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// One source fans out to two or three independent 2FF chains and reconverges.
module shared_reconvergence #(parameter int CHAINS = 2, parameter int RECONV = 1) (
  input  logic clk_a,
  input  logic rst_a_n,
  input  logic d,
  input  logic clk_b,
  input  logic rst_b_n,
  output logic joined,
  output logic other
);
  logic src_q;
  logic a1, a2, b1, b2, c1, c2;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n)
      src_q <= 1'b0;
    else
      src_q <= d;
  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) begin
      a1 <= 1'b0;
      a2 <= 1'b0;
      b1 <= 1'b0;
      b2 <= 1'b0;
      c1 <= 1'b0;
      c2 <= 1'b0;
    end else begin
      a1 <= src_q;
      a2 <= a1;
      b1 <= src_q;
      b2 <= b1;
      c1 <= src_q;
      c2 <= c1;
    end
  assign joined = RECONV ? ((CHAINS == 2) ? (a2 ^ b2) : (a2 ^ b2 ^ c2)) : a2;
  assign other = (CHAINS == 2) ? b2 : c2;
endmodule
