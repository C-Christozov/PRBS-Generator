module prbs_checker 
    #(
    parameter integer WIDTH = 7,
    parameter [WIDTH-1:0] TAPS = 7'b1100000,
    parameter [WIDTH-1:0] SEED = {{(WIDTH-1){1'b0}}, 1'b1}
)(
    input  wire             clk,
    input  wire             rst,
    input  wire             en,
    input  wire             data_in,
    output wire             expected_bit,
    output reg              error,
    output wire [WIDTH-1:0] state
);
    reg  [WIDTH-1:0] lfsr;
    wire feedback;

    assign feedback     = ^(lfsr & TAPS);
    assign expected_bit = lfsr[WIDTH-1];
    assign state        = lfsr;

    always @(posedge clk) begin
        if (rst) begin
            lfsr  <= SEED;
            error <= 1'b0;
        end else if (en) begin
            error <= (data_in != expected_bit);
            lfsr  <= {lfsr[WIDTH-2:0], feedback};
        end
    end

endmodule