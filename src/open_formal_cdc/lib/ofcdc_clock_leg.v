// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Well-formed input clock for T-CLKMUX: each phase lasts at least MIN_STEPS steps.
module ofcdc_clock_leg #(parameter MIN_STEPS = 2, parameter W = 32) (
  input act,
  input v
);
  reg prev = 1'b0;
  reg [W-1:0] phase = MIN_STEPS;
  always @($global_clock) begin
    prev <= v;
    if (v != prev) phase <= 1;
    else if (phase != {W{1'b1}}) phase <= phase + 1'b1;
  end
  always @(*) if (act && v != prev) assume (phase >= MIN_STEPS);
endmodule
