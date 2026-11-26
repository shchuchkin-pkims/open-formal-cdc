// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Reset synchronizer with asynchronous assertion and staged synchronous deassertion.
// BAD = 1 releases both stages together; BAD = 2 removes asynchronous assertion.
module reset_sync #(parameter int BAD = 0) (
  input  logic clk,
  input  logic rst_n,
  output logic out
);
  logic s1, s2;
  logic [1:0] sync_stages;
  assign sync_stages = {s2, s1};
  assign out = s2;

  generate if (BAD == 2) begin : g_no_async
    always_ff @(posedge clk)
      if (!rst_n) begin s1 <= 1'b0; s2 <= 1'b0; end
      else begin s1 <= 1'b1; s2 <= s1; end
  end else begin : g_async
    always_ff @(posedge clk or negedge rst_n)
      if (!rst_n) begin s1 <= 1'b0; s2 <= 1'b0; end
      else begin s1 <= 1'b1; s2 <= (BAD == 1) ? 1'b1 : s1; end
  end endgenerate
endmodule
