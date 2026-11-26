// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Two-stage reset synchronizer used to validate the M6 reset-release model.
module reset_chain (
  input  logic clk,
  input  logic rst_n,
  output logic sync_q
);
  logic meta_q;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin
      meta_q <= 1'b0;
      sync_q <= 1'b0;
    end else begin
      meta_q <= 1'b1;
      sync_q <= meta_q;
    end
endmodule
