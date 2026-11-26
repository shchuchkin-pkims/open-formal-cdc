// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// RDC capture guard: no capture while the source is in reset or during the first
// RELEASE_CYCLES destination edges after reset release. The destination edge is used
// explicitly so independent source and destination resets are handled.
module ofcdc_rdc_capture #(parameter RELEASE_CYCLES = 1) (
  input act,
  input cap,
  input src_rst_n,
  input dst_valid
);
  reg [RELEASE_CYCLES-1:0] released = {RELEASE_CYCLES{1'b0}};
  generate
    if (RELEASE_CYCLES == 1) begin : g_one
      always @($global_clock)
        if (!src_rst_n) released <= 1'b0;
        else if (cap)   released <= 1'b1;
    end else begin : g_many
      always @($global_clock)
        if (!src_rst_n) released <= {RELEASE_CYCLES{1'b0}};
        else if (cap)   released <= {released[RELEASE_CYCLES-2:0], 1'b1};
    end
  endgenerate
  wire allowed = &released;
  always @(*)
    if (act && cap && dst_valid) begin
      p_capture: assert (allowed);
      c_capture: cover (allowed);
    end
endmodule
