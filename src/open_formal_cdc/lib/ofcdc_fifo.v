// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// T-FIFO: protocol check of an asynchronous FIFO on its interface.
// - occupancy: a write is accepted when wr_en && !wr_full at a write edge, a read when
//   rd_en && !rd_empty at a read edge; the FIFO never accepts a write when it holds
//   DEPTH words and never a read when it is empty (flags are correct);
// - data: one written word, chosen by the solver, is read back unchanged and in order
//   (read_latency 0: rd_data shows the head word while rd_empty is low).
// The monitor is cleared only when both sides are in reset, so a reset of one side
// during operation is visible (duplicate or lost words).
// TICKS = 1: flops sample the values of the edge step; TICKS = 0 (clk2fflogic): the
// values of the previous step.
module ofcdc_fifo #(parameter DW = 1, parameter DEPTH = 4, parameter TICKS = 1) (
  input           act_w, act_r,
  input           edge_w, edge_r,
  input           wr_en, wr_full,
  input  [DW-1:0] wr_data,
  input           rd_en, rd_empty,
  input  [DW-1:0] rd_data
);
  localparam CW = $clog2(DEPTH + 2) + 1;
  reg          acc_w_q, acc_r_q;
  reg [DW-1:0] wd_q, rd_q;
  always @($global_clock) begin
    acc_w_q <= wr_en && !wr_full;
    acc_r_q <= rd_en && !rd_empty;
    wd_q    <= wr_data;
    rd_q    <= rd_data;
  end
  wire          fire_w = act_w && edge_w && (TICKS ? (wr_en && !wr_full) : acc_w_q);
  wire          fire_r = act_r && edge_r && (TICKS ? (rd_en && !rd_empty) : acc_r_q);
  wire [DW-1:0] wdat   = TICKS ? wr_data : wd_q;
  wire [DW-1:0] rdat   = TICKS ? rd_data : rd_q;
  wire          both   = act_w && act_r;

  reg [CW-1:0] occ = 0;          // words in the FIFO by the interface contract
  reg          armed = 1'b0;     // a word is tracked
  reg          done = 1'b0;      // the tracked word was read
  reg [DW-1:0] tw;               // tracked word
  reg [CW-1:0] ahead;            // words in front of the tracked word
  wire         pick = $anyseq;
  always @($global_clock)
    if (!act_w && !act_r) begin
      occ <= 0; armed <= 1'b0; done <= 1'b0;
    end else begin
      occ <= occ + fire_w - fire_r;
      if (fire_w && pick && !armed) begin
        armed <= 1'b1;
        tw    <= wdat;
        ahead <= occ - fire_r;
      end
      if (armed && !done && fire_r) begin
        if (ahead == 0) done <= 1'b1;
        else ahead <= ahead - 1'b1;
      end
    end
  always @(*)
    if (both) begin
      if (fire_w) p_no_overflow: assert (occ < DEPTH || fire_r);
      if (fire_r) p_no_underflow: assert (occ > 0);
      if (armed && !done && fire_r && ahead == 0) p_data: assert (rdat == tw);
      c_full: cover (occ == DEPTH);
      c_tracked: cover (armed && done);
    end
endmodule
