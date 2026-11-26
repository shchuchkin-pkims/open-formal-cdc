// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// E6: register x in domain A, toggles on clk_a edges.
module flop (input logic clk_a, input logic en, output logic x);
  always_ff @(posedge clk_a) if (en) x <= ~x;
endmodule
