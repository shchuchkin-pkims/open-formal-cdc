// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// M6: after reset deassertion, a receiving flop may remain in reset for one
// additional clock edge. Injection is independent for every instance.
module ofcdc_msi_reset #(parameter ACTIVE_LOW = 1) (
  input clk,
  input msi_en,
  input rst,
  output rst_seen,
  output msi_alt,
  output msi_skip
);
  reg prev = 1'b0;
  always @(posedge clk) prev <= rst;
  wire release = ACTIVE_LOW ? rst : ~rst;
  wire pick = $anyseq;
  wire late = msi_en && release && (prev != rst) && pick;
  assign rst_seen = ACTIVE_LOW ? (rst & ~late) : (rst | late);
  assign msi_alt = late;
  assign msi_skip = msi_en && release && (prev != rst) && !late;
endmodule
