// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// RDC-001: reset deassertion must coincide with an edge of the destination clock.
module ofcdc_reset_release #(parameter ACTIVE_LOW = 1) (
  input act,
  input cap,
  input rst
);
  wire rst_n = ACTIVE_LOW ? rst : ~rst;
  reg prev = 1'b0;
  always @($global_clock) prev <= rst_n;
  always @(*)
    if (act && prev && !rst_n) begin
      p_release: assert (cap);
      c_release: cover (cap);
    end
endmodule
