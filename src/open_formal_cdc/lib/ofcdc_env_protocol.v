// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Protocol assumption on one clock domain. The wrapper supplies Boolean literals.
// T = 0: always a3
// T = 1: always a1 -> a3
// T = 2: always a1 -> next a3
// T = 3: always (a1 && a2) -> a3
// T = 4: always (a1 && a2) -> next a3
// T = 5: always (a1 && next a2) -> next a3
module ofcdc_env_protocol #(parameter T = 0, parameter ASSERT = 0) (
  input clk,
  input act,
  input a1,
  input a2,
  input a3
);
  reg a1_q, a2_q;
  reg valid = 1'b0;
  always @(posedge clk) begin
    a1_q  <= a1;
    a2_q  <= a2;
    valid <= act;
  end
  wire ok = (T == 0) ? a3 :
            (T == 1) ? (!a1 || a3) :
            (T == 2) ? (!a1_q || a3) :
            (T == 3) ? (!(a1 && a2) || a3) :
            (T == 4) ? (!(a1_q && a2_q) || a3) :
                       (!(a1_q && a2) || a3);
  wire check_en = act && ((T == 0 || T == 1 || T == 3) ? 1'b1 : valid);
  generate
    if (ASSERT) begin : g_assert
      always @(*) if (check_en) p_env: assert (ok);
      always @(*) c_env_act: cover (check_en);
    end else begin : g_assume
      always @(*) if (check_en) assume (ok);
    end
  endgenerate
endmodule
