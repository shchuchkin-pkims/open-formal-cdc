// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Tick model: one global clock gclk, domain clock = gclk & tick_<domain>.
// formalff -declockgate is expected to turn this into a clock enable.
module ofcdc_wrap (input gclk, input tick_a, input tick_b, input inc);
  always @(*) assume (tick_a | tick_b);      // at least one domain fires on every step
  reg [1:0] rc = 2'd0;
  always @(posedge gclk) if (rc != 2'd3) rc <= rc + 2'd1;
  wire rst_n = (rc == 2'd3);
`ifdef ICG
  reg en_a, en_b;                            // ICG: enable latch transparent while gclk = 0
  always @* if (!gclk) begin en_a = tick_a; en_b = tick_b; end
  wire clk_a = gclk & en_a;
  wire clk_b = gclk & en_b;
`else
  wire clk_a = gclk & tick_a;
  wire clk_b = gclk & tick_b;
`endif
  wire [3:0] ptr_b, s0;
  dut u_dut (.clk_a(clk_a), .rst_a_n(rst_n), .inc(inc),
             .clk_b(clk_b), .rst_b_n(rst_n), .ptr_b(ptr_b), .ofcdc_s0(s0));
  ofcdc_gray #(.W(4)) u_chk (.clk(clk_a), .rst_n(rst_n), .v(s0));
endmodule
