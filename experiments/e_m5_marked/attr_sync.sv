// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Two synchronizer stages packed into one attributed vector flip-flop.
module attr_sync #(parameter int STAGES = 2) (
  input  logic clk_a,
  input  logic rst_a_n,
  input  logic set_a,
  input  logic clk_b,
  input  logic rst_b_n,
  output logic q
);
  logic src_q;
  (* async_reg = "true" *) logic [STAGES-1:0] sync_q;
  always_ff @(posedge clk_a or negedge rst_a_n)
    if (!rst_a_n)
      src_q <= 1'b0;
    else if (set_a)
      src_q <= 1'b1;
  always_ff @(posedge clk_b or negedge rst_b_n)
    if (!rst_b_n)
      sync_q <= '0;
    else
      sync_q <= {sync_q[STAGES-2:0], src_q};
  assign q = sync_q[STAGES-1];
endmodule
