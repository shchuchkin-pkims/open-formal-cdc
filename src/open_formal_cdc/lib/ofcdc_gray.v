// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-GRAY: at most one bit of the bus changes per source clock edge.
// Attach to the source registers (before the synchronizers).
// Style valid for both time models: state in flops clocked by the domain clock,
// checks in always @(*) only (no edge-triggered $check cells).
module ofcdc_gray #(parameter W = 1) (
  input         clk,   // source domain clock
  input         act,   // source domain is out of reset
  input [W-1:0] v
);
  reg [W-1:0] prev;
  reg         valid = 1'b0;   // prev was loaded by an edge outside reset
  always @(posedge clk) begin
    prev  <= v;
    valid <= act;
  end
  // After edge k: v was written by edge k, prev by edge k-1.
  wire [W-1:0] diff = v ^ prev;
  always @(*)
    if (valid && act) begin
      p_gray: assert ((diff & (diff - 1'b1)) == 0);
      c_change: cover (diff != 0);
    end
endmodule
