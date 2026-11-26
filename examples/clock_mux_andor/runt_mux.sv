// A control-domain select is synchronized into clk0, one of the
// muxed clocks, and a plain mux switches the clocks. The select is
// synchronous to a muxed leg, yet a switch can still cut a clk1
// phase short: formal/clock_switch.sv finds such a runt pulse under
// the same traffic assumption the glitch-free mux needs. Must
// report CDC-010.
module cdc010_leg_synced_select_runt (
    input  logic clk0,
    input  logic clk1,
    input  logic rst0,
    input  logic rst1,
    input  logic cs,
    input  logic sel_d,
    output logic clk_out,
    output logic [1:0] on,
    output logic q
);
    // The select comes from a control-domain register.
    logic sel;
    always_ff @(posedge cs) sel <= sel_d;

    logic s_m, s_s;
    always_ff @(posedge clk0) begin
        s_m <= sel;
        s_s <= s_m;
    end
    assign clk_out = s_s ? clk1 : clk0;
    assign on = s_s ? 2'b10 : 2'b01;

    always_ff @(posedge clk_out) q <= !q;
endmodule
