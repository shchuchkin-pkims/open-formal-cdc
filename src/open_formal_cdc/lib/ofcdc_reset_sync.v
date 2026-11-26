// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Reset synchronizer: asynchronous assertion and synchronous, staged deassertion.
module ofcdc_reset_sync #(parameter N = 2) (
  input             clk,
  input             rst_n,
  input [N-1:0]     v
);
  reg [N-1:0] model;
  always @(posedge clk or negedge rst_n)
    if (!rst_n) model <= {N{1'b0}};
    else        model <= {model[N-2:0], 1'b1};
  always @(*) begin
    p_stages: assert (v == model);
    c_release: cover (rst_n && model != {N{1'b1}});
  end
endmodule
