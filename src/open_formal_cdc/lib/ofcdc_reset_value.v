// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// RDC-002: while the source reset is asserted, the destination must hold its reset value.
module ofcdc_reset_value #(parameter VALUE = 0, parameter ACTIVE_LOW = 1) (
  input act,
  input reset,
  input dst
);
  wire asserted = ACTIVE_LOW ? !reset : reset;
  always @(*)
    if (act && asserted) begin
      p_value: assert (dst == VALUE);
      c_reset: cover (1'b1);
    end
endmodule
