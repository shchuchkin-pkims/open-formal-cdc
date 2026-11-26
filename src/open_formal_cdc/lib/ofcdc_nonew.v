// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-META (no invented values): the destination of a crossing never shows a value that
// the source has never held. The solver picks any value X; if the destination takes
// X, the source must have held X before. With the metastability model on the first
// synchronizer stage, a bus whose bits change together (not Gray) can be captured as
// a mixture of old and new bits that the source never had.
module ofcdc_nonew #(parameter W = 1) (
  input         act,      // both domains out of reset
  input [W-1:0] src,      // source register
  input [W-1:0] dst       // destination register (last synchronizer stage)
);
  wire [W-1:0] x = $anyconst;
  reg          seen = 1'b0;   // the source has held X
  reg [W-1:0]  dst_q;
  reg          started = 1'b0;
  always @($global_clock) begin
    if (src == x) seen <= 1'b1;
    dst_q   <= dst;
    started <= act;
  end
  always @(*)
    if (started && act && dst == x && dst != dst_q) begin
      p_nonew: assert (seen || src == x);
      c_new: cover (1'b1);
    end
endmodule
