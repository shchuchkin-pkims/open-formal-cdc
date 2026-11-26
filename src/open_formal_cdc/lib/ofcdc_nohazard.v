// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-GLITCH function-hazard form (model M4): the logic in front of a synchronizer is
// evaluated on an independent old/new view of every input. Each bit may take its value
// at the previous or current destination edge. A skewed output is allowed only if D
// has already held that value in the current destination period. This distinguishes
// function hazards from legitimate short pulses. Gate-delay hazards are outside the model.
module ofcdc_nohazard #(parameter W = 1) (
  input         cap,
  input [W-1:0] d,
  input [W-1:0] f
);
  wire [W-1:0] x = $anyconst;
  reg [W-1:0] d_ref;
  reg         seen = 1'b0;
  reg         valid = 1'b0;
  always @($global_clock) begin
    if (cap) begin
      d_ref <= d;
      seen  <= (d == x);
      valid <= 1'b1;
    end else if (d == x) begin
      seen <= 1'b1;
    end
  end
  always @(*)
    if (cap && valid) begin
      p_nohazard: assert (f != x || f == d || seen || x == d);
      c_change: cover (d != d_ref);
      c_skew: cover (f != d);
    end
endmodule
