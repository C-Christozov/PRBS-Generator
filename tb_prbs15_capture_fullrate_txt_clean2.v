`timescale 1ns/1ps

module tb_prbs15_capture_fullrate_txt_clean;

    localparam integer NUM_FAST_CYCLES = 32767;
    localparam [14:0] DUT_INIT_STATE = 15'b000000010000000;

    reg clk_fast;
    reg clk_slow;
    reg rst;
    reg en_half;
    reg phase;

    wire [1:0] half_ref;
    wire [14:0] half_ref_state;

    wire mux_a, mux_b, mux_out;
    wire xor_top, xor_bot;
    wire t2_dbg, b3_dbg, t3_dbg, b4_dbg, latch_dbg;
    wire [14:0] state_vector;

    reg serialized_ref;

    integer f_serial_ref, f_mux_out;
    integer i;

    prbs15_half_rate ref (
        .clk(clk_fast),
        .rst(rst),
        .en(en_half),
        .prbs_out(half_ref),
        .state(half_ref_state)
    );

    prbs15_half_rate_core_struct #(
        .INIT_STATE(DUT_INIT_STATE)
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
        clk_fast = 1'b0;
        forever #5 clk_fast = ~clk_fast;
    end

    initial begin
        clk_slow = 1'b0;
        forever #10 clk_slow = ~clk_slow;
    end

    always @(posedge clk_fast) begin
        if (rst) begin
            phase   <= 1'b0;
            en_half <= 1'b0;
        end else begin
            phase   <= ~phase;
            en_half <= ~phase;
        end
    end

    always @(posedge clk_fast) begin
        if (rst) begin
            serialized_ref <= 1'b0;
        end else begin
            if (phase == 1'b0)
                serialized_ref <= half_ref[1];
            else
                serialized_ref <= half_ref[0];
        end
    end

    initial begin
        f_serial_ref = $fopen("serialized_ref.txt", "w");
        f_mux_out    = $fopen("mux_out.txt", "w");

        rst = 1'b1;
        phase = 1'b0;
        en_half = 1'b0;
        serialized_ref = 1'b0;

        repeat (2) @(posedge clk_fast);
        rst = 1'b0;

        for (i = 0; i < NUM_FAST_CYCLES; i = i + 1) begin
            @(posedge clk_fast);
            #1;
            $fwrite(f_serial_ref, "%0d\n", serialized_ref);
            $fwrite(f_mux_out, "%0d\n", mux_out);
        end

        $fclose(f_serial_ref);
        $fclose(f_mux_out);
        $finish;
    end

endmodule
