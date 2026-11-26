// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Automatic M5 proposal for direct, logic-between-stages and enabled receivers.
module auto_m5 #(parameter int LOGIC = 0, parameter int ENABLED = 0, parameter int INLINE = 0) (
  input  logic clk_a,
  input  logic rst_a_n,
  input  logic set_a,
  input  logic clk_b,
  input  logic rst_b_n,
  input  logic pass_b,
  input  logic en_b,
  output logic sync_q
);
  logic src_q;
  logic meta_q;
  wire second_d = (LOGIC != 0) ? (meta_q & pass_b) : meta_q;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n)
      src_q <= 1'b0;
    else if (set_a)
      src_q <= 1'b1;
  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n)
      meta_q <= 1'b0;
    else
      meta_q <= src_q;
  generate
    if (ENABLED != 0) begin : g_enabled
      always_ff @(posedge clk_b or negedge rst_b_n)
        if (!rst_b_n)
          sync_q <= 1'b0;
        else if (en_b)
          sync_q <= second_d;
    end else if (INLINE != 0) begin : g_inline
      always_ff @(posedge clk_b or negedge rst_b_n)
        if (!rst_b_n)
          sync_q <= 1'b0;
        else
          sync_q <= meta_q & pass_b;
    end else begin : g_free_running
      always_ff @(posedge clk_b or negedge rst_b_n)
        if (!rst_b_n)
          sync_q <= 1'b0;
        else
          sync_q <= second_d;
    end
  endgenerate
endmodule
