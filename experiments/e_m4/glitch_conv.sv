// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Example: a 2-bit state of domain A goes to domain B two ways:
// - through an AND gate in front of a 2FF synchronizer (glitch risk);
// - bit by bit through two synchronizers that meet again in a register of B (convergence).
// BIN = 0: the state steps in Gray order (00 01 11 10), one bit changes at a time: safe.
// BIN = 1: the state counts in binary (01 -> 10 changes two bits): glitch and convergence hazards.

module sync2 (input logic clk, rst_n, d, output logic q);
  logic s1;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin s1 <= 1'b0; q <= 1'b0; end
    else begin s1 <= d; q <= s1; end
endmodule

module glitch_conv #(parameter bit BIN = 0) (
  input  logic       clk_a, rst_a_n, step,
  input  logic       clk_b, rst_b_n,
  output logic       both_b,
  output logic [1:0] st_b
);
  logic [1:0] st;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n) st <= 2'b00;
    else if (step) begin
      if (BIN) st <= st + 2'd1;
      else     st <= {st[0], ~st[1]};      // 00 -> 01 -> 11 -> 10 -> 00
    end

  sync2 u_and (.clk(clk_b), .rst_n(rst_b_n), .d(st[0] & st[1]), .q(both_b));

  logic s0, s1;
  sync2 u_s0 (.clk(clk_b), .rst_n(rst_b_n), .d(st[0]), .q(s0));
  sync2 u_s1 (.clk(clk_b), .rst_n(rst_b_n), .d(st[1]), .q(s1));
  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) st_b <= 2'b00;
    else          st_b <= {s1, s0};
endmodule
