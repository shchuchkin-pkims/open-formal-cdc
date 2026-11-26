// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// RDC capture guard example. MODE = 0 shares resets, MODE = 1 resets only the source,
// MODE = 2 delays capture by one destination edge after source reset release.
module rdc_capture #(parameter int MODE = 0) (
  input  logic clk_a, rst_a_n,
  input  logic clk_b, rst_b_n,
  input  logic valid_in,
  input  logic data_in,
  output logic out_q,
  output logic capture
);
  logic src_rst_n, dst_valid, src_data, dst_data;
  assign src_rst_n = rst_a_n;
  assign dst_valid = (MODE == 2) ? (valid_in & src_rst_n) : valid_in;
  assign capture = dst_valid;

  always_ff @(posedge clk_a or negedge src_rst_n)
    if (!src_rst_n) src_data <= 1'b0;
    else if (!dst_valid) src_data <= data_in;

  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n) begin
      dst_data <= 1'b0;
      out_q    <= 1'b0;
    end else begin
      if (dst_valid) dst_data <= src_data;
      out_q <= dst_data;
    end
endmodule
