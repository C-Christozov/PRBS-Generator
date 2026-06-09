`timescale 1ps/1fs

module tb_prbs15_core_struct_muxout_serialized;

    reg clk_fast;
    reg clk_slow;
    reg rst;
    reg en_half;

    wire [1:0] half_ref;
    wire [14:0] half_ref_state;

    wire mux_a, mux_b, mux_out;
    wire xor_top, xor_bot;
    wire t2_dbg, b3_dbg, t3_dbg, b4_dbg, latch_dbg;
    wire [14:0] state_vector;

    reg phase;
    reg serialized_ref;
    reg serialized_d1, serialized_d2, serialized_d3, serialized_d4;

    integer i;

    prbs15_half_rate ref (
        .clk(clk_fast),
        .rst(rst),
        .en(en_half),
        .prbs_out(half_ref),
        .state(half_ref_state)
    );

    prbs15_half_rate_core_struct #(
        .INIT_STATE(15'b000000000001000)
    ) dut (
        .clk(clk_slow),
        .rst(rst),
        .en(en_half),
        .mux_a(mux_a),
        .mux_b(mux_b),
        .mux_out(mux_out),
        .xor_top(xor_top),
        .xor_bot(xor_bot),
        .t2_dbg(t2_dbg),
        .b3_dbg(b3_dbg),
        .t3_dbg(t3_dbg),
        .b4_dbg(b4_dbg),
        .latch_dbg(latch_dbg),
        .state_vector(state_vector)
    );

    initial begin
        $dumpfile("prbs15_core_struct_muxout_serialized.vcd");
        $dumpvars(0, tb_prbs15_core_struct_muxout_serialized);
    end

    initial clk_fast = 0;
    initial clk_slow = 0;
    always #6.25 clk_fast = ~clk_fast;
    always #12.5 clk_slow = ~clk_slow;

    always @(posedge clk_fast) begin
        if (rst) begin
            phase <= 1'b0;
            en_half <= 1'b0;
        end else begin
            phase <= ~phase;
            en_half <= ~phase;   // advance half-rate model every other fast cycle
        end
    end

    // serialized reference:
    // first fast phase -> half_ref[1]
    // second fast phase -> half_ref[0]
    always @(posedge clk_fast) begin
        if (rst) begin
            serialized_ref <= 1'b0;
            serialized_d1  <= 1'b0;
            serialized_d2  <= 1'b0;
            serialized_d3  <= 1'b0;
            serialized_d4  <= 1'b0;
        end else begin
            serialized_d1 <= serialized_ref;
            serialized_d2 <= serialized_d1;
            serialized_d3 <= serialized_d2;
            serialized_d4 <= serialized_d3;

            if (phase == 1'b0)
                serialized_ref <= half_ref[1];
            else
                serialized_ref <= half_ref[0];
        end
    end

    initial begin
        rst = 1;
        phase = 1'b0;
        en_half = 1'b0;

        #20;
        rst = 0;

        // warm-up
        repeat (20) @(posedge clk_fast);

        for (i = 0; i < 500; i = i + 1) begin
            @(posedge clk_fast);
            #1;

            $display("cycle=%0d phase=%b mux_out=%b sref=%b d1=%b d2=%b d3=%b d4=%b",
                     i, phase, mux_out, serialized_ref, serialized_d1, serialized_d2, serialized_d3, serialized_d4);

            if (mux_out == serialized_ref)
                $display("  MATCH serialized d0");
            else if (mux_out == serialized_d1)
                $display("  MATCH serialized d1");
            else if (mux_out == serialized_d2)
                $display("  MATCH serialized d2");
            else if (mux_out == serialized_d3)
                $display("  MATCH serialized d3");
            else if (mux_out == serialized_d4)
                $display("  MATCH serialized d4");
            else
                $display("  NO MATCH");
        end

        $finish;
    end

endmodule