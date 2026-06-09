`timescale 1ns/1ps

module tb_prbs_core_multipattern;

    reg clk;
    reg rst;
    reg en;
    reg [2:0] seq_sel;

    wire dout;
    wire [30:0] state;
    wire outp;

    prbs_core_multipattern dut (
        .clk(clk),
        .rst(rst),
        .en(en),
        .seq_sel(seq_sel),
        .dout(dout),
        .state(state),
	.outp(outp)
    );

    initial begin
        $dumpfile("prbs_core_multipattern.vcd");
        $dumpvars(0, tb_prbs_core_multipattern);
    end

    initial clk = 0;
    always #5 clk = ~clk;

    integer i;

    initial begin
        rst = 1;
        en  = 0;
        seq_sel = 3'b000; // PRBS-7

        #20;
        rst = 0;
        en  = 1;

        // PRBS-7
        $display("Testing PRBS-7");
        for (i = 0; i < 20; i = i + 1) begin
            @(posedge clk);
            #1;
            $display("t=%0t sel=%b dout=%b state=%b ouput=%b", $time, seq_sel, dout, state, outp);
        end

        // PRBS-10
        seq_sel = 3'b001;
        $display("Testing PRBS-10");
        for (i = 0; i < 20; i = i + 1) begin
            @(posedge clk);
            #1;
            $display("t=%0t sel=%b dout=%b state=%b ouput=%b", $time, seq_sel, dout, state, outp);
        end

        // PRBS-15
        seq_sel = 3'b010;
        $display("Testing PRBS-15");
        for (i = 0; i < 20; i = i + 1) begin
            @(posedge clk);
            #1;
            $display("t=%0t sel=%b dout=%b state=%b ouput=%b", $time, seq_sel, dout, state, outp);
        end

        // PRBS-23
        seq_sel = 3'b011;
        $display("Testing PRBS-23");
        for (i = 0; i < 20; i = i + 1) begin
            @(posedge clk);
            #1;
            $display("t=%0t sel=%b dout=%b state=%b ouput=%b", $time, seq_sel, dout, state, outp);
        end

        // PRBS-31
        seq_sel = 3'b100;
        $display("Testing PRBS-31");
        for (i = 0; i < 20; i = i + 1) begin
            @(posedge clk);
            #1;
            $display("t=%0t sel=%b dout=%b state=%b ouput=%b", $time, seq_sel, dout, state, outp);
        end
        $finish;
    end

endmodule