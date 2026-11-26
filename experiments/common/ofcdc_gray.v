// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-GRAY template (draft): at most one bit changes per source clock edge.
// Read with read_verilog -formal. Style valid for both time models (ticks and clk2fflogic):
// state in edge-clocked flops, assertions in always @(*), no edge-triggered $check cells.
module ofcdc_gray #(parameter W = 4) (
  input         clk,
  input         rst_n,
  input [W-1:0] v
);
  reg [W-1:0] prev;
  reg         valid = 1'b0;          // prev was loaded by at least one edge outside reset
  always @(posedge clk) begin
    prev  <= v;
    valid <= rst_n;
  end
  // After edge k: v was written by edge k, prev by edge k-1.
  wire [W-1:0] diff = v ^ prev;
  always @(*)
    if (valid && rst_n) begin
      p_gray: assert ((diff & (diff - 1'b1)) == 0);
      c_change: cover (diff != 0);
    end
endmodule
