// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Two independent clock domains feed one AND cone before a synchronizer.
// BIN = 0: Gray order does not prevent capture-period hazards with independent domains.
// BIN = 1: binary order; 01 -> 10 can produce an intermediate 11 and a hazard.
// BIN = 2: paired 00 <-> 11 is safe in one domain, but hazardous with independent sources.

module sync2 (input logic clk, rst_n, d, output logic q);
  logic s1;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin s1 <= 1'b0; q <= 1'b0; end
    else begin s1 <= d; q <= s1; end
endmodule

module async_hazard #(parameter int BIN = 0) (
  input  logic clk_a, rst_a_n, step_a,
  input  logic clk_b, rst_b_n, step_b,
  input  logic clk_c, rst_c_n,
  output logic out
);
  logic st0, st1;
  logic [1:0] nxt;
  always_comb begin
    if (BIN == 1)      nxt = {st1, st0} + 2'd1;
    else if (BIN == 2) nxt = ~{st1, st0};
    else               nxt = {st0, ~st1};
  end

  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n) st0 <= 1'b0;
    else if (step_a) st0 <= nxt[0];

  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) st1 <= 1'b0;
    else if (step_b) st1 <= nxt[1];

  sync2 u_and (.clk(clk_c), .rst_n(rst_c_n), .d(st0 & st1), .q(out));
endmodule
