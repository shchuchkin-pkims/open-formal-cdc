// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Scalable CDC array: N independent Gray buses and combinational flag cones.
// BUG = 0: correct; BUG = 1: binary bus; BUG = 2: missing destination bus stage.
module cdc_array #(
  parameter int N = 16,
  parameter int W = 8,
  parameter int BUG = 0
) (
  input  logic             clk_a,
  input  logic             rst_a_n,
  input  logic             inc,
  input  logic             clk_b,
  input  logic             rst_b_n,
  output logic [N*W-1:0]   data_b,
  output logic [N-1:0]     flag_b
);
  logic [N*W-1:0] bin;
  logic [N*W-1:0] ptr_a;
  logic [N*W-1:0] sync1;
  logic [N-1:0]   flag_sync1;

  for (genvar ch = 0; ch < N; ch++) begin : g_channel
    wire [W-1:0] bin_nx = inc ? bin[ch*W +: W] + W'(1) : bin[ch*W +: W];
    always_ff @(posedge clk_a or negedge rst_a_n) begin
      if (!rst_a_n) begin
        bin[ch*W +: W]   <= '0;
        ptr_a[ch*W +: W] <= '0;
      end else begin
        bin[ch*W +: W] <= bin_nx;
        ptr_a[ch*W +: W] <= (BUG == 1) ? bin_nx : (bin_nx ^ (bin_nx >> 1));
      end
    end

    always_ff @(posedge clk_b or negedge rst_b_n) begin
      if (!rst_b_n) begin
        sync1[ch*W +: W] <= '0;
        data_b[ch*W +: W] <= '0;
      end else begin
        sync1[ch*W +: W] <= ptr_a[ch*W +: W];
        if (BUG == 2)
          data_b[ch*W +: W] <= ptr_a[ch*W +: W];
        else
          data_b[ch*W +: W] <= sync1[ch*W +: W];
      end
    end

    always_ff @(posedge clk_b or negedge rst_b_n) begin
      if (!rst_b_n) begin
        flag_sync1[ch] <= 1'b0;
        flag_b[ch]     <= 1'b0;
      end else begin
        flag_sync1[ch] <= ptr_a[ch*W] & ptr_a[ch*W+1];
        flag_b[ch]     <= flag_sync1[ch];
      end
    end
  end
endmodule
