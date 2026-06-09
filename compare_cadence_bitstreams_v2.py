#!/usr/bin/env python3
"""
BER / bitstream comparator for two Cadence/ViVA waveform CSV exports. This script compares a reference waveform against a waveform export (csv) from Cadence.

Bit rule:
    voltage > threshold  -> 1
    voltage <= threshold -> 0

Example, 10 Gb/s:
    py compare_cadence_bitstreams.py PRBS31_ref.csv PRBS31_DFF_delay.csv --bit-rate 10e9 --threshold -1.65

Example 80 Gb/s, -3.3 V to 0 V:
    py compare_cadence_bitstreams.py ref.csv delayed.csv --bit-rate 80e9 --threshold -1.65 --min-overlap-fraction 0.8
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


def load_cadence_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray, str, str]:
    path = Path(path)
    df = pd.read_csv(path)

    if df.shape[1] < 2:
        raise ValueError(f"{path} must contain at least two columns: time and voltage.")

    time_col = df.columns[0]
    voltage_col = df.columns[1]

    time = pd.to_numeric(df.iloc[:, 0], errors="coerce").to_numpy()
    voltage = pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy()

    valid = np.isfinite(time) & np.isfinite(voltage)
    time = time[valid]
    voltage = voltage[valid]

    if len(time) < 2:
        raise ValueError(f"{path} does not contain enough valid waveform samples.")

    order = np.argsort(time)
    return time[order], voltage[order], time_col, voltage_col


def crop_waveform(
    time: np.ndarray,
    voltage: np.ndarray,
    start_time: float | None,
    stop_time: float | None,
) -> tuple[np.ndarray, np.ndarray]:
    mask = np.ones_like(time, dtype=bool)

    if start_time is not None:
        mask &= time >= start_time
    if stop_time is not None:
        mask &= time <= stop_time

    time_c = time[mask]
    voltage_c = voltage[mask]

    if len(time_c) < 2:
        raise ValueError("Crop window contains fewer than two valid samples.")

    return time_c, voltage_c


def sample_to_bits(
    time: np.ndarray,
    voltage: np.ndarray,
    bit_rate: float,
    threshold: float,
    phase_ui: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    ui = 1.0 / bit_rate
    sample_times = np.arange(time[0] + phase_ui * ui, time[-1], ui)

    if len(sample_times) == 0:
        raise ValueError("No sample points generated. Check time range and bit rate.")

    sampled_voltage = np.interp(sample_times, time, voltage)
    bits = (sampled_voltage > threshold).astype(np.uint8)

    return sample_times, sampled_voltage, bits


def bit_array_to_string(bits: np.ndarray) -> str:
    return "".join(str(int(b)) for b in bits)


def write_bit_string_csv(
    input_path: str | Path,
    bits: np.ndarray,
    sample_times: np.ndarray,
    sampled_voltage: np.ndarray,
) -> Path:
    input_path = Path(input_path)
    output_path = input_path.with_name(input_path.stem + "_bit_string.csv")

    df = pd.DataFrame({
        "bit_index": np.arange(len(bits), dtype=int),
        "sample_time_s": sample_times,
        "sampled_voltage_v": sampled_voltage,
        "bit": bits.astype(int),
    })

    compact = bit_array_to_string(bits)
    df["bit_string_compact"] = ""
    if len(df) > 0:
        df.loc[0, "bit_string_compact"] = compact

    df.to_csv(output_path, index=False)
    return output_path


def compare_with_shift(
    reference_bits: np.ndarray,
    test_bits: np.ndarray,
    shift_bits: int,
) -> dict:
    """
    Convention:
        Positive shift_bits means the test waveform is delayed relative to the reference.
        In comparison, test[shift:] is aligned with reference[0:].
    """
    n_ref = len(reference_bits)
    n_test = len(test_bits)

    if shift_bits >= 0:
        ref_start = 0
        test_start = shift_bits
        n_compare = min(n_ref, n_test - test_start)
    else:
        ref_start = -shift_bits
        test_start = 0
        n_compare = min(n_ref - ref_start, n_test)

    if n_compare <= 0:
        return {
            "shift_bits": int(shift_bits),
            "n_compared_bits": 0,
            "bit_errors": np.nan,
            "matching_bits": np.nan,
            "ber": np.nan,
            "match_fraction": np.nan,
            "longest_matching_run_bits": 0,
        }

    ref_segment = reference_bits[ref_start:ref_start + n_compare]
    test_segment = test_bits[test_start:test_start + n_compare]

    matches = ref_segment == test_segment
    bit_errors = int(np.count_nonzero(~matches))
    matching_bits = int(np.count_nonzero(matches))
    ber = bit_errors / n_compare
    match_fraction = matching_bits / n_compare

    longest_run = 0
    current_run = 0
    for value in matches:
        if value:
            current_run += 1
            longest_run = max(longest_run, current_run)
        else:
            current_run = 0

    return {
        "shift_bits": int(shift_bits),
        "n_compared_bits": int(n_compare),
        "bit_errors": bit_errors,
        "matching_bits": matching_bits,
        "ber": float(ber),
        "match_fraction": float(match_fraction),
        "longest_matching_run_bits": int(longest_run),
    }


def sweep_shifts(
    reference_bits: np.ndarray,
    test_bits: np.ndarray,
    max_shift_bits: int,
    min_overlap_bits: int,
) -> pd.DataFrame:
    rows = []
    for shift in range(-max_shift_bits, max_shift_bits + 1):
        row = compare_with_shift(reference_bits, test_bits, shift)
        row["valid_overlap"] = row["n_compared_bits"] >= min_overlap_bits
        rows.append(row)

    return pd.DataFrame(rows)


def select_best_shift(results: pd.DataFrame) -> pd.Series:
    """
    Select best alignment.

    This avoids the old bug where a 6-bit perfect overlap could win.

    Priority:
    1. valid overlap only
    2. highest matching bits
    3. lowest bit errors
    4. lowest BER
    5. highest compared bits
    6. smallest absolute shift
    """
    valid = results[(results["valid_overlap"]) & (~results["ber"].isna())].copy()

    if valid.empty:
        raise ValueError(
            "No valid alignment found. Reduce --min-overlap-bits, reduce --min-overlap-fraction, "
            "or increase the waveform duration."
        )

    valid["abs_shift"] = valid["shift_bits"].abs()

    valid = valid.sort_values(
        by=[
            "matching_bits",
            "bit_errors",
            "ber",
            "n_compared_bits",
            "abs_shift",
        ],
        ascending=[
            False,
            True,
            True,
            False,
            True,
        ],
    )

    return valid.iloc[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare two Cadence CSV waveforms as sampled bitstreams.")
    parser.add_argument("reference_csv", help="Reference Cadence waveform CSV.")
    parser.add_argument("test_csv", help="Delayed/non-ideal/test Cadence waveform CSV.")
    parser.add_argument("--bit-rate", type=float, required=True, help="Bit rate in bit/s, e.g. 10e9 or 80e9.")
    parser.add_argument("--threshold", type=float, required=True, help="Decision threshold voltage.")
    parser.add_argument("--phase-ui", type=float, default=0.5, help="Sampling phase inside each UI. Default: 0.5.")
    parser.add_argument("--start-time", type=float, default=None, help="Common analysis start time in seconds.")
    parser.add_argument("--stop-time", type=float, default=None, help="Common analysis stop time in seconds.")
    parser.add_argument("--ref-start-time", type=float, default=None, help="Reference-specific start time. Overrides --start-time.")
    parser.add_argument("--test-start-time", type=float, default=None, help="Test-specific start time. Overrides --start-time.")
    parser.add_argument("--ref-stop-time", type=float, default=None, help="Reference-specific stop time. Overrides --stop-time.")
    parser.add_argument("--test-stop-time", type=float, default=None, help="Test-specific stop time. Overrides --stop-time.")
    parser.add_argument("--max-shift-bits", type=int, default=None, help="Maximum absolute shift to sweep.")
    parser.add_argument("--min-overlap-bits", type=int, default=None, help="Minimum overlap required for a candidate shift.")
    parser.add_argument("--min-overlap-fraction", type=float, default=0.8, help="Minimum overlap as fraction of shorter bitstream. Default: 0.8.")
    parser.add_argument("--output-metrics", default=None, help="Output metrics CSV file.")
    parser.add_argument("--output-shift-sweep", default=None, help="Output CSV containing all shift sweep results.")
    args = parser.parse_args()

    ui = 1.0 / args.bit_rate

    ref_time, ref_voltage, ref_time_col, ref_voltage_col = load_cadence_csv(args.reference_csv)
    test_time, test_voltage, test_time_col, test_voltage_col = load_cadence_csv(args.test_csv)

    ref_start = args.ref_start_time if args.ref_start_time is not None else args.start_time
    test_start = args.test_start_time if args.test_start_time is not None else args.start_time
    ref_stop = args.ref_stop_time if args.ref_stop_time is not None else args.stop_time
    test_stop = args.test_stop_time if args.test_stop_time is not None else args.stop_time

    ref_time, ref_voltage = crop_waveform(ref_time, ref_voltage, ref_start, ref_stop)
    test_time, test_voltage = crop_waveform(test_time, test_voltage, test_start, test_stop)

    ref_sample_times, ref_sampled_voltage, ref_bits = sample_to_bits(
        ref_time, ref_voltage, args.bit_rate, args.threshold, args.phase_ui
    )
    test_sample_times, test_sampled_voltage, test_bits = sample_to_bits(
        test_time, test_voltage, args.bit_rate, args.threshold, args.phase_ui
    )

    ref_bit_file = write_bit_string_csv(args.reference_csv, ref_bits, ref_sample_times, ref_sampled_voltage)
    test_bit_file = write_bit_string_csv(args.test_csv, test_bits, test_sample_times, test_sampled_voltage)

    n_min = min(len(ref_bits), len(test_bits))

    if args.max_shift_bits is None:
        # Default: only sweep shifts that still preserve the requested minimum overlap.
        # With min_overlap_fraction=0.8 and 5900 bits, this limits |shift| to about 1180 bits.
        min_overlap_bits = args.min_overlap_bits
        if min_overlap_bits is None:
            min_overlap_bits = int(np.ceil(args.min_overlap_fraction * n_min))
        max_shift_bits = max(0, n_min - min_overlap_bits)
    else:
        max_shift_bits = args.max_shift_bits

    if args.min_overlap_bits is None:
        min_overlap_bits = int(np.ceil(args.min_overlap_fraction * n_min))
    else:
        min_overlap_bits = args.min_overlap_bits

    if min_overlap_bits < 1:
        raise ValueError("--min-overlap-bits must be at least 1.")

    if min_overlap_bits > n_min:
        raise ValueError("--min-overlap-bits cannot exceed the shorter bitstream length.")

    max_shift_bits = min(max_shift_bits, n_min - 1)

    sweep_df = sweep_shifts(ref_bits, test_bits, max_shift_bits, min_overlap_bits)
    sweep_df["shift_seconds"] = sweep_df["shift_bits"] * ui
    sweep_df["shift_ps"] = sweep_df["shift_seconds"] * 1e12

    if args.output_shift_sweep is None:
        test_path = Path(args.test_csv)
        sweep_path = test_path.with_name(test_path.stem + "_shift_sweep.csv")
    else:
        sweep_path = Path(args.output_shift_sweep)
    sweep_df.to_csv(sweep_path, index=False)

    best = select_best_shift(sweep_df)

    best_shift_bits = int(best["shift_bits"])
    best_shift_seconds = best_shift_bits * ui
    longest_run_bits = int(best["longest_matching_run_bits"])
    full_overlap = int(best["n_compared_bits"]) == n_min
    full_match = (int(best["bit_errors"]) == 0) and full_overlap

    metrics = {
        "reference_csv": str(args.reference_csv),
        "test_csv": str(args.test_csv),
        "reference_bit_string_csv": str(ref_bit_file),
        "test_bit_string_csv": str(test_bit_file),
        "shift_sweep_csv": str(sweep_path),
        "reference_time_column": ref_time_col,
        "reference_voltage_column": ref_voltage_col,
        "test_time_column": test_time_col,
        "test_voltage_column": test_voltage_col,
        "bit_rate_bps": args.bit_rate,
        "ui_s": ui,
        "ui_ps": ui * 1e12,
        "threshold_v": args.threshold,
        "sampling_phase_ui": args.phase_ui,
        "sampling_phase_s": args.phase_ui * ui,
        "sampling_phase_ps": args.phase_ui * ui * 1e12,
        "reference_bits": int(len(ref_bits)),
        "test_bits": int(len(test_bits)),
        "shorter_bitstream_bits": int(n_min),
        "max_shift_bits_swept": int(max_shift_bits),
        "min_overlap_bits": int(min_overlap_bits),
        "min_overlap_fraction": float(min_overlap_bits / n_min),
        "best_shift_bits": best_shift_bits,
        "best_shift_seconds": best_shift_seconds,
        "best_shift_ps": best_shift_seconds * 1e12,
        "best_shift_interpretation": "positive means test waveform is delayed relative to reference",
        "n_compared_bits_at_best_shift": int(best["n_compared_bits"]),
        "bit_errors_at_best_shift": int(best["bit_errors"]),
        "matching_bits_at_best_shift": int(best["matching_bits"]),
        "ber_at_best_shift": float(best["ber"]),
        "match_fraction_at_best_shift": float(best["match_fraction"]),
        "match_percent_at_best_shift": float(best["match_fraction"] * 100.0),
        "longest_matching_run_bits": longest_run_bits,
        "longest_matching_run_seconds": longest_run_bits * ui,
        "longest_matching_run_ps": longest_run_bits * ui * 1e12,
        "full_overlap_at_best_shift": bool(full_overlap),
        "full_match_at_best_shift": bool(full_match),
    }

    if args.output_metrics is None:
        test_path = Path(args.test_csv)
        metrics_path = test_path.with_name(test_path.stem + "_ber_metrics.csv")
    else:
        metrics_path = Path(args.output_metrics)
    pd.DataFrame([metrics]).to_csv(metrics_path, index=False)

    print("\n=== BER / bitstream comparison summary ===")
    print(f"Reference CSV:              {args.reference_csv}")
    print(f"Test CSV:                   {args.test_csv}")
    print(f"Bit rate:                   {args.bit_rate:.6e} bit/s")
    print(f"UI:                         {ui * 1e12:.6g} ps")
    print(f"Threshold:                  {args.threshold:.6g} V")
    print(f"Sampling phase:             {args.phase_ui:.3f} UI ({args.phase_ui * ui * 1e12:.6g} ps)")
    print(f"Reference bits:             {len(ref_bits)}")
    print(f"Test bits:                  {len(test_bits)}")
    print(f"Minimum overlap required:   {min_overlap_bits} bits ({100 * min_overlap_bits / n_min:.2f}% of shorter stream)")
    print(f"Shift sweep range:          {-max_shift_bits} to {max_shift_bits} bits")
    print(f"Best shift:                 {best_shift_bits} bits")
    print(f"Best shift time:            {best_shift_seconds:.6e} s ({best_shift_seconds * 1e12:.6g} ps)")
    print(f"Compared bits:              {int(best['n_compared_bits'])}")
    print(f"Bit errors:                 {int(best['bit_errors'])}")
    print(f"BER:                        {float(best['ber']):.6e}")
    print(f"Match percentage:           {float(best['match_fraction'] * 100):.4f}%")
    print(f"Longest matching run:       {longest_run_bits} bits")
    print(f"Longest matching run time:  {longest_run_bits * ui:.6e} s ({longest_run_bits * ui * 1e12:.6g} ps)")
    print(f"Full overlap at best shift: {full_overlap}")
    print(f"Full match at best shift:   {full_match}")
    print("\n=== Files written ===")
    print(f"Metrics CSV:                {metrics_path}")
    print(f"Shift sweep CSV:            {sweep_path}")
    print(f"Reference bit-string CSV:   {ref_bit_file}")
    print(f"Test bit-string CSV:        {test_bit_file}")


if __name__ == "__main__":
    main()
