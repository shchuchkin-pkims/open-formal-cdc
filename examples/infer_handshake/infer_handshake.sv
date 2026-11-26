// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// One-cycle acknowledge for an environment-driven request.
module infer_handshake (
  input  logic clk,
  input  logic rst_n,
  input  logic req,
  output logic ack
);
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) ack <= 1'b0;
    else        ack <= req;
endmodule
