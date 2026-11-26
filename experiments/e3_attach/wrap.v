// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Wrapper: design (after rename -output) + checker module. Time model: clk2fflogic.
module ofcdc_wrap (input clk_a, input clk_b, input inc);
  reg [1:0] rc = 2'd0;                       // reset held for the first 3 steps
  always @($global_clock) if (rc != 2'd3) rc <= rc + 2'd1;
  wire rst_n = (rc == 2'd3);
  wire [3:0] ptr_b, s0;
  dut u_dut (.clk_a(clk_a), .rst_a_n(rst_n), .inc(inc),
             .clk_b(clk_b), .rst_b_n(rst_n), .ptr_b(ptr_b), .ofcdc_s0(s0));
  ofcdc_gray #(.W(4)) u_chk (.clk(clk_a), .rst_n(rst_n), .v(s0));
endmodule
