// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Example: Gray-coded pointer from domain A, 2FF bus synchronizer in domain B.
// MODE = 0: correct Gray code
// MODE = 1: broken, binary code on the bus
// MODE = 2: broken, Gray code of a counter that steps by 2 (two bits may change)

module gray_tx #(parameter int W = 4, parameter int MODE = 0) (
  input  logic         clk, rst_n, inc,
  output logic [W-1:0] ptr
);
  logic [W-1:0] bin, bin_nx;
  assign bin_nx = inc ? bin + ((MODE == 2) ? W'(2) : W'(1)) : bin;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin
      bin <= '0;
      ptr <= '0;
    end else begin
      bin <= bin_nx;
      ptr <= (MODE == 1) ? bin_nx : (bin_nx ^ (bin_nx >> 1));
    end
endmodule

module sync2 #(parameter int W = 1) (
  input  logic         clk, rst_n,
  input  logic [W-1:0] d,
  output logic [W-1:0] q
);
  logic [W-1:0] s1;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin
      s1 <= '0;
      q  <= '0;
    end else begin
      s1 <= d;
      q  <= s1;
    end
endmodule

module gray_sync #(parameter int W = 4, parameter int MODE = 0) (
  input  logic         clk_a, rst_a_n, inc,
  input  logic         clk_b, rst_b_n,
  output logic [W-1:0] ptr_b
);
  logic [W-1:0] ptr_a;
  gray_tx #(.W(W), .MODE(MODE)) u_tx (.clk(clk_a), .rst_n(rst_a_n), .inc(inc), .ptr(ptr_a));
  sync2   #(.W(W))              u_sync (.clk(clk_b), .rst_n(rst_b_n), .d(ptr_a), .q(ptr_b));
endmodule
