// SPDX-License-Identifier: Apache-2.0
// Author: Shchuchkin E. Yu. <shchuchkin-pkims@yandex.ru>
// Experiment property: the synchronized pointer (Gray -> binary) never overtakes
// the real source pointer. The source counter saturates, no wrap-around.
module ofcdc_nooverrun #(parameter W = 4, parameter GRAY = 1) (
  input         rst_n,
  input [W-1:0] bin_src,
  input [W-1:0] ptr_dst
);
  function [W-1:0] g2b(input [W-1:0] g);
    integer i;
    begin
      g2b[W-1] = g[W-1];
      for (i = W - 2; i >= 0; i = i - 1) g2b[i] = g2b[i+1] ^ g[i];
    end
  endfunction
  wire [W-1:0] dst_bin = GRAY ? g2b(ptr_dst) : ptr_dst;
  always @(*) if (rst_n) begin
    p_nooverrun: assert (dst_bin <= bin_src);
    c_moved: cover (dst_bin != 0);
  end
endmodule
