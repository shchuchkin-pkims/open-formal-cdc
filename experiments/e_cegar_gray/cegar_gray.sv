// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Gray-code abstraction example. aux_q is constantly one in the good design,
// so 01 -> 11 is a one-bit transition. Abstracting aux_q permits 01 -> 10,
// which changes both bits. BAD=1 makes that transition real.
module cegar_gray #(parameter int BAD = 0) (
  input  logic       clk,
  input  logic       rst_n,
  input  logic       inc,
  output logic [1:0] ptr_q
);
  logic       aux_q;
  logic [1:0] next;

  always_comb begin
    case (ptr_q)
      2'b00:   next = 2'b01;
      2'b01:   next = (BAD != 0) ? (aux_q ? 2'b10 : 2'b11) : (aux_q ? 2'b11 : 2'b10);
      2'b11:   next = 2'b10;
      default: next = 2'b00;
    endcase
  end

  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin
      ptr_q <= 2'b00;
      aux_q <= 1'b1;
    end else begin
      aux_q <= 1'b1;
      if (inc) ptr_q <= next;
    end
endmodule
