// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// E-PAST: which SVA features yosys-slang accepts (build 20261118).
module p (input logic clk, input logic a);
  logic b = 1'b0, ok = 1'b0;
  always_ff @(posedge clk) begin b <= a; ok <= 1'b1; end
`ifdef T_PAST
  always_ff @(posedge clk) if (ok) a_past: assert (b == $past(a));
`endif
`ifdef T_STABLE
  logic c = 1'b0;
  always_ff @(posedge clk) if (ok) a_stable: assert ($stable(c));
`endif
`ifdef T_PROP
  a_prop: assert property (@(posedge clk) a |=> b);
`endif
`ifdef T_PROP_BAD
  a_prop_bad: assert property (@(posedge clk) a |=> !b);
`endif
endmodule
