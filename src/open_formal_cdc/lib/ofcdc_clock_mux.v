// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-CLKMUX: no runt phase on a muxed clock. A phase is measured in global steps.
module ofcdc_clock_mux #(parameter MIN_STEPS = 2, parameter W = 32) (
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
  always @(*)
    if (act && v != prev) begin
      p_phase: assert (phase >= MIN_STEPS);
      c_change: cover (phase >= MIN_STEPS);
    end
endmodule
