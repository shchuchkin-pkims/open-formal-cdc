// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-GLITCH / T-CONV: among the given source bits at most one changes per global step.
// - glitch: the foreign-domain inputs of the logic in front of a synchronizer; if two
//   of them change together, the logic output may glitch and the glitch may be captured;
// - convergence: the sources of synchronizers whose outputs meet in one logic cone of
//   the destination; if two change together, the destination may see a combination
//   that never existed (the synchronizers may resolve on different cycles).
module ofcdc_onechange #(parameter W = 1) (
  input         act,
  input [W-1:0] v
);
  reg [W-1:0] prev;
  reg         started = 1'b0;
  always @($global_clock) begin
    prev    <= v;
    started <= act;
  end
  wire [W-1:0] diff = v ^ prev;
  always @(*)
    if (started && act) begin
      p_onechange: assert ((diff & (diff - 1'b1)) == 0);
      c_change: cover (diff != 0);
    end
endmodule
