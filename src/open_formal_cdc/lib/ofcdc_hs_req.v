// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-HS: handshake request protocol. The request changes only when the synchronized
// acknowledge has caught up with it (ack_s == req): a 4-phase request rises after the
// acknowledge fell and falls after it rose; a toggle request toggles again only after
// the acknowledge toggled back. Otherwise the destination may still be capturing.
module ofcdc_hs_req (
  input clk,      // source clock
  input act,      // source domain out of reset
  input req,      // request (source domain register)
  input ack_s     // acknowledge synchronized into the source domain
);
  reg prev_req, prev_ack;
  reg valid = 1'b0;
  always @(posedge clk) begin
    prev_req <= req;
    prev_ack <= ack_s;
    valid    <= act;
  end
  always @(*)
    if (valid && act) begin
      if (req != prev_req) p_req: assert (prev_ack == prev_req);
      c_req: cover (req != prev_req);
    end
endmodule
