// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Example: data bus from domain A to domain B under a toggle handshake.
// A loads data and toggles req; B synchronizes req, captures the data on the req
// toggle (capture enable "cap") and returns ack; A waits for ack before new data.
// BAD = 1: A also updates the data while a transfer is in progress.

module sync2 (input logic clk, rst_n, d, output logic q);
  logic s1;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin s1 <= 1'b0; q <= 1'b0; end
    else begin s1 <= d; q <= s1; end
endmodule

module hs_tx #(parameter int W = 8, parameter bit BAD = 0) (
  input  logic         clk, rst_n, go,
  input  logic [W-1:0] din,
  input  logic         ack_s,        // ack toggle synchronized to clk
  output logic         req,          // request toggle
  output logic [W-1:0] data
);
  logic busy, ack_q;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin
      busy <= 1'b0; req <= 1'b0; data <= '0; ack_q <= 1'b0;
    end else begin
      ack_q <= ack_s;
      if (!busy && go) begin
        data <= din;
        req  <= ~req;
        busy <= 1'b1;
      end else if (BAD && go) begin
        data <= din;                   // bug: data changes during the transfer
      end
      if (busy && (ack_s != ack_q)) busy <= 1'b0;
    end
endmodule

module hs_rx #(parameter int W = 8) (
  input  logic         clk, rst_n,
  input  logic         req_s,        // req toggle synchronized to clk
  input  logic [W-1:0] data_in,
  output logic         ack,
  output logic         cap,          // capture enable
  output logic [W-1:0] data_out
);
  logic req_q;
  assign cap = (req_s != req_q);
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin
      req_q <= 1'b0; ack <= 1'b0; data_out <= '0;
    end else begin
      req_q <= req_s;
      if (cap) begin
        data_out <= data_in;
        ack      <= req_s;
      end
    end
endmodule

module handshake_mux #(parameter int W = 8, parameter bit BAD = 0) (
  input  logic         clk_a, rst_a_n, go,
  input  logic [W-1:0] din,
  input  logic         clk_b, rst_b_n,
  output logic [W-1:0] dout
);
  logic req, req_s, ack, ack_s, cap;
  logic [W-1:0] data_a;
  hs_tx #(.W(W), .BAD(BAD)) u_tx (.clk(clk_a), .rst_n(rst_a_n), .go(go), .din(din),
                                  .ack_s(ack_s), .req(req), .data(data_a));
  sync2 u_req_sync (.clk(clk_b), .rst_n(rst_b_n), .d(req), .q(req_s));
  hs_rx #(.W(W)) u_rx (.clk(clk_b), .rst_n(rst_b_n), .req_s(req_s), .data_in(data_a),
                       .ack(ack), .cap(cap), .data_out(dout));
  sync2 u_ack_sync (.clk(clk_a), .rst_n(rst_a_n), .d(ack), .q(ack_s));
endmodule
