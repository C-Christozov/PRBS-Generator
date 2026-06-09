#!/usr/bin/env python3
"""
PRBS7 (Linear)
    python prbs_waveform_verify.py wave.csv --bit-rate 10e9 --vlow -3.3 --vhigh 0 --order 7 --taps 7 6

PRBS15 (Interleaved)
    python prbs_waveform_verify.py wave.csv --bit-rate 80e9 --vlow -3.3 --vhigh 0 --order 15 --taps 15 14
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def load_cadence_csv(path: str | Path) -> tuple[np.ndarray, np.ndarray]:
    df = pd.read_csv(path)

    if df.shape[1] < 2:
        raise ValueError("CSV must contain at least two columns: time and waveform voltage.")

    time = pd.to_numeric(df.iloc[:, 0], errors="coerce").to_numpy()
    voltage = pd.to_numeric(df.iloc[:, 1], errors="coerce").to_numpy()

    valid = np.isfinite(time) & np.isfinite(voltage)
    time = time[valid]
    voltage = voltage[valid]

    if len(time) < 2:
        raise ValueError("Not enough valid waveform samples found.")

    order = np.argsort(time)
    return time[order], voltage[order]


def voltage_to_logic(voltage: np.ndarray, threshold: float) -> np.ndarray:
    return (voltage > threshold).astype(np.uint8)


def sample_waveform(
    time: np.ndarray,
    voltage: np.ndarray,
    bit_rate: float,
    threshold: float,
    phase_ui: float = 0.5,
    start_time: float | None = None,
    stop_time: float | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:

    ui = 1.0 / bit_rate

    if start_time is None:
        start_time = time[0]
    if stop_time is None:
        stop_time = time[-1]

    first_sample_time = start_time + phase_ui * ui
    sample_times = np.arange(first_sample_time, stop_time, ui)

    sampled_voltage = np.interp(sample_times, time, voltage)
    sampled_bits = voltage_to_logic(sampled_voltage, threshold)

    return sample_times, sampled_voltage, sampled_bits


def generate_prbs(order: int, taps: Iterable[int], length: int, seed: int | None = None) -> np.ndarray:

    if seed is None:
        state = np.ones(order, dtype=np.uint8)
    else:
        if seed <= 0 or seed >= (1 << order):
            raise ValueError(f"Seed must be between 1 and 2^{order}-1.")
        state = np.array([(seed >> i) & 1 for i in range(order - 1, -1, -1)], dtype=np.uint8)

    tap_indices = [order - tap for tap in taps]
    out = np.empty(length, dtype=np.uint8)

    for i in range(length):
        out[i] = state[-1]
        feedback = np.bitwise_xor.reduce(state[tap_indices])
        state[1:] = state[:-1]
        state[0] = feedback

    return out


def best_cyclic_compare(
    measured: np.ndarray,
    expected_period: np.ndarray,
    allow_invert: bool = True,
    allow_reverse: bool = False,
) -> dict:
    """
    Compare measured bits to cyclic shifts of the expected PRBS period.
    Returns the best match.
    """
    measured = np.asarray(measured, dtype=np.uint8)
    expected_period = np.asarray(expected_period, dtype=np.uint8)

    candidates = [("normal", expected_period)]

    if allow_invert:
        candidates.append(("inverted", 1 - expected_period))

    if allow_reverse:
        rev = expected_period[::-1]
        candidates.append(("reversed", rev))
        if allow_invert:
            candidates.append(("inverted+reversed", 1 - rev))

    best = None

    for mode, candidate in candidates:
        period = len(candidate)
        for shift in range(period):
            repeated = np.resize(np.roll(candidate, shift), len(measured))
            errors = int(np.count_nonzero(measured != repeated))
            ber = errors / len(measured)

            result = {
                "mode": mode,
                "shift_bits": shift,
                "errors": errors,
                "total_bits": len(measured),
                "ber": ber,
            }

            if best is None or errors < best["errors"]:
                best = result

    return best


def sweep_sampling_phase(
    time: np.ndarray,
    voltage: np.ndarray,
    bit_rate: float,
    threshold: float,
    expected_period: np.ndarray,
    phases: np.ndarray,
    start_time: float | None = None,
    stop_time: float | None = None,
) -> list[dict]:
    """Sweep sampling phase over one UI and compare each phase."""
    results = []

    for phase in phases:
        _, _, bits = sample_waveform(
            time=time,
            voltage=voltage,
            bit_rate=bit_rate,
            threshold=threshold,
            phase_ui=float(phase),
            start_time=start_time,
            stop_time=stop_time,
        )

        comparison = best_cyclic_compare(bits, expected_period)
        comparison["phase_ui"] = float(phase)
        results.append(comparison)

    return sorted(results, key=lambda x: x["errors"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify Cadence PRBS waveform export against expected PRBS.")
    parser.add_argument("csv", help="Cadence/ViVA exported CSV file.")
    parser.add_argument("--bit-rate", type=float, required=True, help="Output bit rate in bit/s, e.g. 80e9.")
    parser.add_argument("--vlow", type=float, default=-3.3, help="Logic-low voltage.")
    parser.add_argument("--vhigh", type=float, default=0.0, help="Logic-high voltage.")
    parser.add_argument("--threshold", type=float, default=None, help="Logic threshold. Default is midpoint of vlow and vhigh.")
    parser.add_argument("--phase-ui", type=float, default=0.5, help="Sampling phase as fraction of UI. Default: 0.5.")
    parser.add_argument("--start-time", type=float, default=None, help="Optional start time in seconds.")
    parser.add_argument("--stop-time", type=float, default=None, help="Optional stop time in seconds.")
    parser.add_argument("--order", type=int, default=7, help="PRBS order. Default: 7.")
    parser.add_argument("--taps", type=int, nargs="+", default=[7, 6], help="PRBS taps in polynomial notation. Default: 7 6.")
    parser.add_argument("--seed", type=int, default=None, help="Optional integer LFSR seed. Default: all ones.")
    parser.add_argument("--no-compare", action="store_true", help="Only extract sampled bits; do not compare.")
    parser.add_argument("--sweep-phase", action="store_true", help="Sweep sampling phase from 0.05 UI to 0.95 UI.")
    parser.add_argument("--output-bits", default="sampled_bits.txt", help="File to write sampled bitstream.")

    args = parser.parse_args()

    threshold = args.threshold
    if threshold is None:
        threshold = 0.5 * (args.vlow + args.vhigh)

    time, voltage = load_cadence_csv(args.csv)

    dt = np.diff(time)
    print("\n=== Waveform summary ===")
    print(f"Samples:              {len(time)}")
    print(f"Time range:           {time[0]:.6e} s to {time[-1]:.6e} s")
    print(f"Median timestep:      {np.median(dt):.6e} s")
    print(f"Voltage range:        {np.min(voltage):.4g} V to {np.max(voltage):.4g} V")
    print(f"Logic threshold:      {threshold:.4g} V")
    print(f"Bit rate:             {args.bit_rate:.6e} bit/s")
    print(f"UI:                   {1 / args.bit_rate:.6e} s")

    sample_times, sampled_voltage, sampled_bits = sample_waveform(
        time=time,
        voltage=voltage,
        bit_rate=args.bit_rate,
        threshold=threshold,
        phase_ui=args.phase_ui,
        start_time=args.start_time,
        stop_time=args.stop_time,
    )

    bit_string = "".join(str(int(b)) for b in sampled_bits)
    Path(args.output_bits).write_text(bit_string + "\n")

    print("\n=== Sampling summary ===")
    print(f"Sampled bits:         {len(sampled_bits)}")
    print(f"Sampling phase:       {args.phase_ui:.3f} UI")
    print(f"Output bit file:      {args.output_bits}")
    print(f"First 128 bits:       {bit_string[:128]}")

    if args.no_compare:
        return

    expected_len = 2**args.order - 1
    expected_period = generate_prbs(args.order, args.taps, expected_len, seed=args.seed)

    if args.sweep_phase:
        phases = np.linspace(0.05, 0.95, 19)
        phase_results = sweep_sampling_phase(
            time=time,
            voltage=voltage,
            bit_rate=args.bit_rate,
            threshold=threshold,
            expected_period=expected_period,
            phases=phases,
            start_time=args.start_time,
            stop_time=args.stop_time,
        )
        best = phase_results[0]
    else:
        best = best_cyclic_compare(sampled_bits, expected_period)

    print("\n=== PRBS comparison ===")
    print(f"PRBS order:           {args.order}")
    print(f"PRBS taps:            {args.taps}")
    if args.sweep_phase:
        print(f"Best phase:           {best['phase_ui']:.3f} UI")
    print(f"Best mode:            {best['mode']}")
    print(f"Best cyclic shift:    {best['shift_bits']} bits")
    print(f"Bit errors:           {best['errors']} / {best['total_bits']}")
    print(f"BER over export:      {best['ber']:.6e}")

    if best["errors"] == 0:
        print("\nPASS: sampled waveform matches the expected PRBS sequence.")
    else:
        print("\nWARNING: mismatch remains. Check PRBS tap convention, output polarity, start-up cycles, or sampling phase.")


if __name__ == "__main__":
    main()
