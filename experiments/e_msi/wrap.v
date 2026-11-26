// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// E-MSI wrapper. TICKS: tick time model (ICG + declockgate), otherwise clk2fflogic.
// MSI: metastability model on D of the first synchronizer stage. BAD: binary code.
module ofcdc_wrap (
`ifdef TICKS
  input gclk, input tick_a, input tick_b,
`else
  input clk_a, input clk_b,
`endif
  input inc
);
`ifdef TICKS
  always @(*) assume (tick_a | tick_b);
  reg [1:0] rc = 2'd0;
  always @(posedge gclk) if (rc != 2'd3) rc <= rc + 2'd1;
  reg en_a, en_b;
  always @* if (!gclk) begin en_a = tick_a; en_b = tick_b; end
  wire clk_a = gclk & en_a;
  wire clk_b = gclk & en_b;
  localparam TM = 1;
`else
  reg [1:0] rc = 2'd0;
  always @($global_clock) if (rc != 2'd3) rc <= rc + 2'd1;
  localparam TM = 0;
`endif
  wire rst_n = (rc == 2'd3);
`ifdef MSI
  localparam MSI_EN = 1'b1;
`else
  localparam MSI_EN = 1'b0;
`endif
`ifdef BAD
  localparam GRAY = 0;
`else
  localparam GRAY = 1;
`endif
  wire [3:0] ptr_b, bin_a, mo0, mi0;
  wire alt;
  dut u_dut (.clk_a(clk_a), .rst_a_n(rst_n), .inc(inc), .clk_b(clk_b), .rst_b_n(rst_n),
             .ptr_b(ptr_b), .ofcdc_s1(bin_a), .ofcdc_mo0(mo0), .ofcdc_mi0(mi0));
  ofcdc_msi_d #(.W(4), .TICKS(TM)) u_msi (.msi_en(MSI_EN), .d(mo0), .d_seen(mi0), .msi_alt(alt));
  ofcdc_nooverrun #(.W(4), .GRAY(GRAY)) u_chk (.rst_n(rst_n), .bin_src(bin_a), .ptr_dst(ptr_b));
  always @(*) if (rst_n) c_msi_alt: cover (alt);
endmodule
