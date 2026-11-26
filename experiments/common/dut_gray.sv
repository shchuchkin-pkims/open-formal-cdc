// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Stage 0 experiments: Gray counter in domain A, 2FF bus synchronizer in domain B.
// BAD=1: broken variant, the bus carries binary code.

module gray_tx #(parameter int W = 4, parameter bit BAD = 0) (
  input  logic         clk, rst_n, inc,
  output logic [W-1:0] ptr
);
  logic [W-1:0] bin, bin_nx;
  assign bin_nx = (inc && bin != {W{1'b1}}) ? bin + 1'b1 : bin;   // saturating: no wrap-around
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin bin <= '0; ptr <= '0; end
    else begin
      bin <= bin_nx;
      ptr <= BAD ? bin_nx : (bin_nx ^ (bin_nx >> 1));
    end
endmodule

module sync2 #(parameter int W = 1) (
  input  logic         clk, rst_n,
  input  logic [W-1:0] d,
  output logic [W-1:0] q
);
  logic [W-1:0] s1;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin s1 <= '0; q <= '0; end
    else begin s1 <= d; q <= s1; end
endmodule

module dut #(parameter int W = 4, parameter bit BAD = 0) (
  input  logic         clk_a, rst_a_n, inc,
  input  logic         clk_b, rst_b_n,
  output logic [W-1:0] ptr_b
);
  logic [W-1:0] ptr_a;
  gray_tx #(.W(W), .BAD(BAD)) u_tx (.clk(clk_a), .rst_n(rst_a_n), .inc(inc), .ptr(ptr_a));
  sync2   #(.W(W))            u_sync (.clk(clk_b), .rst_n(rst_b_n), .d(ptr_a), .q(ptr_b));
endmodule
