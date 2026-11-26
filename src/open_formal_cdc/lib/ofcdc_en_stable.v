// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-EN (data stable under the capture enable; Plassan "Stability", Kebaili en_d):
// while the destination capture enable is active, the source data does not change
// since the last destination clock edge. Hence at the capture edge the data was
// stable over the whole window between two destination edges.
module ofcdc_en_stable #(parameter W = 1) (
  input         clk,    // destination domain clock
  input         act,    // destination domain is out of reset
  input         en,     // capture enable (destination domain)
  input [W-1:0] data    // data from the source domain
);
  reg [W-1:0] d_last;
  reg         valid = 1'b0;
  always @(posedge clk) begin
    d_last <= data;
    valid  <= act;
  end
  always @(*)
    if (valid && act) begin
      if (en) p_stable: assert (data == d_last);
      c_capture: cover (en);
      c_data_change: cover (data != d_last);
    end
endmodule
