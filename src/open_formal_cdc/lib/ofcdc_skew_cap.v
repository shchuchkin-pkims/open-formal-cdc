// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Independent old/new skew over one destination-clock period. Each input bit may
// take its value at the previous or current destination edge. The first edge after
// reset establishes the reference; no skew is introduced before it.
module ofcdc_skew_cap #(parameter W = 1) (
  input          cap,
  input  [W-1:0] d,
  output [W-1:0] d_seen,
  output         alt
);
  reg [W-1:0] ref;
  reg         valid = 1'b0;
  always @($global_clock)
    if (cap) begin
      ref   <= d;
      valid <= 1'b1;
    end
  wire [W-1:0] pick = $anyseq;
  assign d_seen = valid ? ((pick & ref) | (~pick & d)) : d;
  assign alt = valid && (d_seen != d);
endmodule
