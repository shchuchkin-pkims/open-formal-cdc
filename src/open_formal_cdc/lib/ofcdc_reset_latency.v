// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Reset deassertion latency: the tail must release within MAX_CYCLES receiver edges
// after the source reset releases. ACTIVE_LOW = 0 inverts both reset inputs.
module ofcdc_reset_latency #(parameter MAX_CYCLES = 2, parameter W = 16, parameter ACTIVE_LOW = 1) (
  input clk,
  input act,
  input src_rst,
  input tail_rst
);
  reg src_prev = 1'b0;
  reg [W-1:0] delay = 1'b0;
  wire src_n = ACTIVE_LOW ? src_rst : ~src_rst;
  wire tail_n = ACTIVE_LOW ? tail_rst : ~tail_rst;
  always @(posedge clk) begin
    src_prev <= src_n;
    if (!src_n) delay <= 0;
    else if (delay < {W{1'b1}}) delay <= delay + 1'b1;
  end
  always @(*)
    if (act && src_prev && !tail_n) begin
      p_latency: assert (delay <= MAX_CYCLES);
      c_release: cover (delay > 0);
    end
endmodule
