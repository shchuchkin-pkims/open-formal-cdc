// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// A flop must capture stable data within STABLE_EDGES receiver clocks. A delayed
// cap samples the post-edge state, then registers it for a phase-independent check.
module ofcdc_settled #(parameter W = 1, parameter STABLE_EDGES = 2, parameter CNT_W = 16) (
  input cap,
  input act,
  input [W-1:0] data,
  input [W-1:0] dst
);
  reg cap_q = 1'b0;
  reg [W-1:0] data_prev;
  reg [CNT_W-1:0] stable = {CNT_W{1'b0}};
  reg started = 1'b0;
  reg check_valid = 1'b0;
  reg [W-1:0] check_data, check_dst;
  reg [CNT_W-1:0] check_stable;
  wire same = started && data == data_prev;
  wire [CNT_W-1:0] stable_next = same && stable < {CNT_W{1'b1}} ? stable + 1'b1 :
                                  same ? stable : {CNT_W{1'b0}};
  always @($global_clock)
    if (!act) begin
      cap_q <= 1'b0;
      data_prev <= data;
      stable <= {CNT_W{1'b0}};
      started <= 1'b0;
      check_valid <= 1'b0;
    end else begin
      cap_q <= cap;
      check_valid <= cap_q;
      if (cap_q) begin
        data_prev <= data;
        stable <= stable_next;
        started <= 1'b1;
        check_data <= data;
        check_dst <= dst;
        check_stable <= stable_next;
      end
    end
  always @(*)
    if (check_valid) begin
      p_settled: assert (check_stable < STABLE_EDGES || check_dst == check_data);
      c_settled: cover (check_stable >= STABLE_EDGES && check_dst == check_data);
    end
endmodule
