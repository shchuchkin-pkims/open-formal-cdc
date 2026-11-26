// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Example: asynchronous FIFO with Gray-coded pointers and 2FF pointer synchronizers
// (classic structure). Read data is combinational from the memory (first word fall-through).
// BUG = 0: correct
// BUG = 1: binary pointers cross the domains (incoherent multi-bit crossing)
// BUG = 2: the write side ignores 'full' (overflow)

module afifo_sync #(parameter int W = 1) (
  input  logic         clk, rst_n,
  input  logic [W-1:0] d,
  output logic [W-1:0] q
);
  logic [W-1:0] s1;
  always_ff @(posedge clk or negedge rst_n)
    if (!rst_n) begin s1 <= '0; q <= '0; end
    else begin s1 <= d; q <= s1; end
endmodule

module async_fifo #(parameter int DW = 4, parameter int AW = 2, parameter int BUG = 0) (
  input  logic          wclk, wrst_n, winc,
  input  logic [DW-1:0] wdata,
  output logic          wfull,
  input  logic          rclk, rrst_n, rinc,
  output logic [DW-1:0] rdata,
  output logic          rempty
);
  logic [DW-1:0] mem [2**AW];
  logic [AW:0] wbin, rbin, wptr, rptr, wq2_rptr, rq2_wptr;

  function automatic logic [AW:0] b2g(input logic [AW:0] b);
    return (BUG == 1) ? b : (b >> 1) ^ b;
  endfunction
  function automatic logic [AW:0] g2b(input logic [AW:0] g);
    logic [AW:0] b;
    if (BUG == 1) return g;
    b[AW] = g[AW];
    for (int i = AW - 1; i >= 0; i--) b[i] = b[i+1] ^ g[i];
    return b;
  endfunction

  // write side
  wire do_write = winc && ((BUG == 2) || !wfull);
  wire [AW:0] wbin_nx = wbin + (do_write ? 1'b1 : 1'b0);
  always_ff @(posedge wclk or negedge wrst_n)
    if (!wrst_n) begin wbin <= '0; wptr <= '0; end
    else begin wbin <= wbin_nx; wptr <= b2g(wbin_nx); end
  always_ff @(posedge wclk)
    if (do_write) mem[wbin[AW-1:0]] <= wdata;
  afifo_sync #(.W(AW+1)) u_wsync (.clk(wclk), .rst_n(wrst_n), .d(rptr), .q(wq2_rptr));
  wire [AW:0] wrbin = g2b(wq2_rptr);
  assign wfull = (wbin[AW] != wrbin[AW]) && (wbin[AW-1:0] == wrbin[AW-1:0]);

  // read side
  wire do_read = rinc && !rempty;
  wire [AW:0] rbin_nx = rbin + (do_read ? 1'b1 : 1'b0);
  always_ff @(posedge rclk or negedge rrst_n)
    if (!rrst_n) begin rbin <= '0; rptr <= '0; end
    else begin rbin <= rbin_nx; rptr <= b2g(rbin_nx); end
  afifo_sync #(.W(AW+1)) u_rsync (.clk(rclk), .rst_n(rrst_n), .d(wptr), .q(rq2_wptr));
  assign rempty = (rbin == g2b(rq2_wptr));
  assign rdata = mem[rbin[AW-1:0]];
endmodule
