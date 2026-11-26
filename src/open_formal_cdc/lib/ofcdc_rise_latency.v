// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Bounded propagation of a monotonic 0 -> 1 control signal. Once src is high,
// dst must become high within MAX_CYCLES receiver edges.
module ofcdc_rise_latency #(parameter MAX_CYCLES = 1, parameter W = 16) (
  input clk,
  input act,
  input src,
  input dst
);
  reg src_prev = 1'b0;
  reg [W-1:0] delay = {W{1'b0}};
  always @(posedge clk) begin
    src_prev <= src;
    if (!src || dst)
      delay <= {W{1'b0}};
    else if (delay < {W{1'b1}})
      delay <= delay + 1'b1;
  end
  always @(*) begin
    if (act && src_prev && src && !dst) begin
      p_latency: assert (delay <= MAX_CYCLES);
      c_wait: cover (delay > 0);
    end
    if (act && src && dst)
      c_risen: cover (1'b1);
  end
endmodule
