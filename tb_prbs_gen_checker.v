`timescale 1ps/1fs

module tb_prbs_gen_checker;

    localparam integer WIDTH = 31;
    localparam [WIDTH-1:0] TAPS = 31'b1001000000000000000000000000000;
    localparam [WIDTH-1:0] SEED = 31'b0000000000000000000000000000001;

    reg clk;
    reg rst;
    reg en;

    wire gen_bit;
    wire [WIDTH-1:0] gen_state;

    wire chk_expected;
    wire chk_error;
    wire [WIDTH-1:0] chk_state;
    
    reg inject_error;
    wire data_to_checker;

    integer i;
    //error injection
    assign data_to_checker = inject_error ? ~gen_bit : gen_bit;

    prbs_generator 
    #(
        .WIDTH(WIDTH),
        .TAPS(TAPS),
        .SEED(SEED)
    ) 
    gen (
        .clk(clk),
        .rst(rst),
        .en(en),
        .prbs_out(gen_bit),
        .state(gen_state)
    );
    
    prbs_checker 
    #(
        .WIDTH(WIDTH),
        .TAPS(TAPS),
        .SEED(SEED)
    ) 
    chk (
        .clk(clk),
        .rst(rst),
        .en(en),
        .data_in(data_to_checker),
        .expected_bit(chk_expected),
        .error(chk_error),
        .state(chk_state)
    );

    initial begin
        $dumpfile("prbs_gen_checker.vcd");
        $dumpvars(0, tb_prbs_gen_checker);
    end

    initial clk = 0;
    always #50 clk = ~clk;

    initial begin
        rst = 1;
        en  = 0;
        inject_error = 0;

        #100;
        rst = 0;
        en  = 1;

        for (i = 0; i < 1500; i = i + 1) begin
            
            @(posedge clk);
            //injects error at cycle == i
            if (i == 22)
                inject_error = 0;
            else
                inject_error = 0;

            #1;

            $display("t=%0t gen=%b data=%b expected=%b error=%b",
                     $time, gen_bit, data_to_checker, chk_expected, chk_error);
        end

        $finish;

    end

endmodule