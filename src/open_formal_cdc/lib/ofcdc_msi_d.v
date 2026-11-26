// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Metastability model M2a (docs/literature/metastability.md): placed on the D net
// of the receiving flop. Every bit that changed close to the receiver edge may be
// captured with its old value. TICKS=1: window for the tick model, TICKS=0: for clk2fflogic.
module ofcdc_msi_d #(parameter W = 1, parameter TICKS = 0) (
  input          msi_en,
  input  [W-1:0] d,
  output [W-1:0] d_seen,
  output         msi_alt
);
  reg [W-1:0] d_q, d_qq;
  always @($global_clock) begin d_q <= d; d_qq <= d_q; end
  wire [W-1:0] chg   = d ^ d_q;                             // bits that changed in this step
  wire [W-1:0] d_old = TICKS ? ((chg & d_q) | (~chg & d))
                             : ((chg & d_q) | (~chg & d_qq));
  wire [W-1:0] pick  = $anyseq;                             // independent choice per bit
  assign d_seen  = msi_en ? ((pick & d_old) | (~pick & d)) : d;
  assign msi_alt = |(d_seen ^ d);
endmodule
