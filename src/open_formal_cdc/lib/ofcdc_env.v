// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Environment assumptions (T-ENV). ASSERT = 0: used as an assumption in every check;
// ASSERT = 1: the twin job that verifies the assumption on the design.
// State is clocked by the global step ($global_clock) so that the same module works
// in both time models; checks are in always @(*).

// constant: v == VALUE once the initial reset is over.
module ofcdc_env_constant #(parameter W = 1, parameter [W-1:0] VALUE = 0, parameter ASSERT = 0) (
  input         act,
  input [W-1:0] v
);
  generate
    if (ASSERT) begin : g_assert
      always @(*) if (act) p_env: assert (v == VALUE);
      always @(*) c_env_act: cover (act);
    end else begin : g_assume
      always @(*) if (act) assume (v == VALUE);
    end
  endgenerate
endmodule

// static: v never changes once the initial reset is over.
module ofcdc_env_static #(parameter W = 1, parameter ASSERT = 0) (
  input         act,
  input [W-1:0] v
);
  reg [W-1:0] prev;
  reg         started = 1'b0;
  always @($global_clock) begin
    prev    <= v;
    started <= act;
  end
  generate
    if (ASSERT) begin : g_assert
      always @(*) if (act && started) p_env: assert (v == prev);
      always @(*) c_env_act: cover (act && started);
    end else begin : g_assume
      always @(*) if (act && started) assume (v == prev);
    end
  endgenerate
endmodule

// onehot0: at most one bit of v is set once the initial reset is over.
module ofcdc_env_onehot0 #(parameter W = 1, parameter ASSERT = 0) (
  input         act,
  input [W-1:0] v
);
  wire ok = (v & (v - 1'b1)) == 0;
  generate
    if (ASSERT) begin : g_assert
      always @(*) if (act) p_env: assert (ok);
      always @(*) c_env_act: cover (act);
    end else begin : g_assume
      always @(*) if (act) assume (ok);
    end
  endgenerate
endmodule

// hamming1: at most one bit of v changes per edge of its clock.
module ofcdc_env_hamming1 #(parameter W = 1, parameter ASSERT = 0) (
  input         clk,
  input         act,
  input [W-1:0] v
);
  reg [W-1:0] prev;
  reg         valid = 1'b0;
  always @(posedge clk) begin
    prev  <= v;
    valid <= act;
  end
  wire [W-1:0] diff = v ^ prev;
  wire ok = (diff & (diff - 1'b1)) == 0;
  generate
    if (ASSERT) begin : g_assert
      always @(*) if (valid && act) p_env: assert (ok);
      always @(*) c_env_act: cover (valid && act);
    end else begin : g_assume
      always @(*) if (valid && act) assume (ok);
    end
  endgenerate
endmodule

// quasi_static: v changes only in a step where 'allow' had the value ALLOW_VAL in this
// or the previous step (for example: configuration changes only while disabled).
module ofcdc_env_quasi_static #(parameter W = 1, parameter ALLOW_VAL = 0, parameter ASSERT = 0) (
  input         act,
  input         allow,
  input [W-1:0] v
);
  reg [W-1:0] prev;
  reg         allow_q;
  reg         started = 1'b0;
  always @($global_clock) begin
    prev    <= v;
    allow_q <= allow;
    started <= act;
  end
  wire may_change = (allow == ALLOW_VAL) || (allow_q == ALLOW_VAL);
  generate
    if (ASSERT) begin : g_assert
      always @(*) if (act && started && !may_change) p_env: assert (v == prev);
      always @(*) c_env_act: cover (act && started && may_change && v != prev);
    end else begin : g_assume
      always @(*) if (act && started && !may_change) assume (v == prev);
    end
  endgenerate
endmodule

// clock_select: select_d must stay equal to sel until on confirms the selected clock.
module ofcdc_env_clock_select #(parameter W = 2, parameter [W-1:0] ON0 = 1,
                                parameter [W-1:0] ON1 = 2, parameter ASSERT = 0, parameter INIT = 0) (
  input         act,
  input         sel_d,
  input         sel,
  input [W-1:0] on
);
  wire [W-1:0] expected = sel ? ON1 : ON0;
  wire settled = (on == expected);
  generate
    if (ASSERT) begin : g_assert
      always @(*) if (act) p_env: assert (settled || sel_d == sel);
      always @(*) c_env_act: cover (act && settled && sel_d != sel);
    end else begin : g_assume
      always @(*) if (!act) assume (sel_d == INIT);
      always @(*) if (act) assume (settled || sel_d == sel);
    end
  endgenerate
endmodule
