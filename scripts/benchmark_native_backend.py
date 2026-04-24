from __future__ import annotations

import argparse
import math
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.native_backend import is_native_available, native_build_sparse_orbits_batch
from app.core.trajectory_engine import build_orbit
from app.models.config import SimulationConfig
from app.models.trajectory import TrajectorySeed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Benchmark native backend against Python orbit building"
    )
    parser.add_argument(
        "--include-1m",
        action="store_true",
        help="Also benchmark 1,000,000 steps.",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=1,
        help="Number of runs per backend and step count.",
    )
    return parser.parse_args()


def make_config(
    *,
    native_enabled: bool,
    sample_mode: str = "every_n",
    sample_step: int = 1,
) -> SimulationConfig:
    return SimulationConfig(
        alpha=0.55,
        beta=1.05,
        n_phase_default=100,
        n_geom_default=25,
        eps=1.0e-9,
        native_enabled=native_enabled,
        native_sample_mode=sample_mode,
        native_sample_step=sample_step,
    )


def make_seed() -> TrajectorySeed:
    return TrajectorySeed(
        id=1,
        wall_start=1,
        d0=0.72,
        tau0=0.08,
    )


def make_scan_seeds(count: int) -> list[TrajectorySeed]:
    seeds: list[TrajectorySeed] = []
    for index in range(count):
        seeds.append(
            TrajectorySeed(
                id=index + 1,
                wall_start=1 if (index % 2 == 0) else 2,
                d0=0.72 - (0.0002 * (index % 50)),
                tau0=0.08 - (0.0005 * (index % 20)),
            )
        )
    return seeds


def benchmark_backend(
    *,
    backend_name: str,
    seed: TrajectorySeed,
    config: SimulationConfig,
    steps: int,
    repeats: int,
) -> tuple[float, object]:
    orbit = None
    best_elapsed = math.inf
    for _ in range(repeats):
        started = time.perf_counter()
        orbit = build_orbit(seed=seed, config=config, steps=steps)
        best_elapsed = min(best_elapsed, time.perf_counter() - started)
    assert orbit is not None
    iterations_per_sec = (steps / best_elapsed) if best_elapsed > 0.0 else math.inf
    print(
        f"{backend_name:>6} | steps={steps:>8} | elapsed={best_elapsed:>8.4f}s | "
        f"rate={iterations_per_sec:>12.1f} it/s | points={len(orbit.points):>8}"
    )
    return best_elapsed, orbit


def benchmark_python_scan_dense(
    *,
    seeds: list[TrajectorySeed],
    steps: int,
    repeats: int,
) -> float:
    best_elapsed = math.inf
    config = make_config(native_enabled=False)
    for _ in range(repeats):
        started = time.perf_counter()
        for seed in seeds:
            build_orbit(seed=seed, config=config, steps=steps)
        best_elapsed = min(best_elapsed, time.perf_counter() - started)
    orbits_per_sec = (len(seeds) / best_elapsed) if best_elapsed > 0.0 else math.inf
    print(
        f"{'py-scan':>11} | seeds={len(seeds):>6} | steps={steps:>8} | "
        f"elapsed={best_elapsed:>8.4f}s | rate={orbits_per_sec:>10.1f} orbits/s"
    )
    return best_elapsed


def benchmark_native_scan_batch(
    *,
    seeds: list[TrajectorySeed],
    steps: int,
    sample_step: int,
    repeats: int,
) -> float:
    best_elapsed = math.inf
    for _ in range(repeats):
        started = time.perf_counter()
        native_build_sparse_orbits_batch(
            d0_list=[seed.d0 for seed in seeds],
            tau0_list=[seed.tau0 for seed in seeds],
            wall0_list=[seed.wall_start for seed in seeds],
            alpha=0.55,
            beta=1.05,
            steps=steps,
            sample_step=sample_step,
            sample_mode="every_n",
        )
        best_elapsed = min(best_elapsed, time.perf_counter() - started)
    orbits_per_sec = (len(seeds) / best_elapsed) if best_elapsed > 0.0 else math.inf
    print(
        f"{'native-batch':>11} | seeds={len(seeds):>6} | steps={steps:>8} | "
        f"elapsed={best_elapsed:>8.4f}s | rate={orbits_per_sec:>10.1f} orbits/s | "
        f"sample_step={sample_step}"
    )
    return best_elapsed


def find_first_divergence(
    python_orbit,
    native_orbit,
    *,
    limit: int,
    tolerance: float = 1.0e-10,
):
    python_points_by_step = {
        point.step_index: point
        for point in python_orbit.points
        if point.step_index < limit
    }
    for native_point in native_orbit.points:
        if native_point.step_index >= limit:
            break
        py_point = python_points_by_step.get(native_point.step_index)
        if py_point is None:
            return {
                "step_index": native_point.step_index,
                "python": None,
                "native": native_point,
                "d_delta": math.inf,
                "tau_delta": math.inf,
            }
        d_delta = abs(py_point.d - native_point.d)
        tau_delta = abs(py_point.tau - native_point.tau)
        if (
            py_point.wall != native_point.wall
            or d_delta > tolerance
            or tau_delta > tolerance
        ):
            return {
                "step_index": py_point.step_index,
                "python": py_point,
                "native": native_point,
                "d_delta": d_delta,
                "tau_delta": tau_delta,
            }
    if native_orbit.points:
        final_step_index = native_orbit.points[-1].step_index
        if final_step_index < limit and final_step_index not in python_points_by_step:
            return {
                "step_index": final_step_index,
                "python": None,
                "native": native_orbit.points[-1],
                "d_delta": math.inf,
                "tau_delta": math.inf,
            }
    if len(native_orbit.points) > len(python_orbit.points):
        last_native_point = native_orbit.points[-1]
        return {
            "step_index": last_native_point.step_index,
            "python": None,
            "native": last_native_point,
            "d_delta": math.inf,
            "tau_delta": math.inf,
        }
    return None


def print_divergence(prefix: str, divergence) -> None:
    if divergence is None:
        return
    py_point = divergence["python"]
    native_point = divergence["native"]
    if py_point is None or native_point is None:
        print(f"{prefix}: first mismatch at compared length boundary step={divergence['step_index']}")
        return
    print(
        f"{prefix}: first mismatch at step {divergence['step_index']} | "
        f"python=(d={py_point.d:.12f}, tau={py_point.tau:.12f}, wall={py_point.wall}) | "
        f"native=(d={native_point.d:.12f}, tau={native_point.tau:.12f}, wall={native_point.wall}) | "
        f"|Δd|={divergence['d_delta']:.3e} |Δtau|={divergence['tau_delta']:.3e}"
    )


def assert_same_final_state(python_orbit, native_orbit, tolerance: float = 1.0e-10) -> None:
    if not python_orbit.points or not native_orbit.points:
        raise AssertionError("one of the compared orbits is empty")
    py_final = python_orbit.points[-1]
    native_final = native_orbit.points[-1]
    if py_final.wall != native_final.wall:
        raise AssertionError(f"wall mismatch: python={py_final.wall} native={native_final.wall}")
    if abs(py_final.d - native_final.d) > tolerance:
        raise AssertionError(f"d mismatch: python={py_final.d} native={native_final.d}")
    if abs(py_final.tau - native_final.tau) > tolerance:
        raise AssertionError(f"tau mismatch: python={py_final.tau} native={native_final.tau}")
    if python_orbit.valid != native_orbit.valid:
        raise AssertionError(
            f"valid mismatch: python={python_orbit.valid} native={native_orbit.valid}"
        )
    if python_orbit.invalid_reason != native_orbit.invalid_reason:
        raise AssertionError(
            "invalid_reason mismatch: "
            f"python={python_orbit.invalid_reason} native={native_orbit.invalid_reason}"
        )


def main() -> int:
    args = parse_args()
    if not is_native_available():
        print("Native backend unavailable. Build the extension first.")
        return 1

    step_counts = [10_000, 50_000, 100_000]
    if args.include_1m:
        step_counts.append(1_000_000)

    seed = make_seed()
    validation_steps = 1_000
    print(f"Validating native correctness on short horizon: {validation_steps} steps")
    validation_python = build_orbit(
        seed=seed,
        config=make_config(native_enabled=False),
        steps=validation_steps,
    )
    validation_native = build_orbit(
        seed=seed,
        config=make_config(native_enabled=True),
        steps=validation_steps,
    )
    divergence = find_first_divergence(
        validation_python,
        validation_native,
        limit=validation_steps,
    )
    if divergence is not None:
        print_divergence("Validation failed", divergence)
        raise AssertionError("native short-horizon validation failed")
    assert_same_final_state(validation_python, validation_native)
    print("Short-horizon validation passed.")

    print(f"Benchmarking with repeats={args.repeats}")
    for steps in step_counts:
        python_elapsed, python_orbit = benchmark_backend(
            backend_name="python",
            seed=seed,
            config=make_config(native_enabled=False),
            steps=steps,
            repeats=args.repeats,
        )
        native_cases = [
            ("native-dense", "dense", 1),
            ("native-10", "every_n", 10),
            ("native-100", "every_n", 100),
            ("native-final", "final", 100),
        ]
        for backend_name, sample_mode, sample_step in native_cases:
            native_elapsed, native_orbit = benchmark_backend(
                backend_name=backend_name,
                seed=seed,
                config=make_config(
                    native_enabled=True,
                    sample_mode=sample_mode,
                    sample_step=sample_step,
                ),
                steps=steps,
                repeats=args.repeats,
            )
            speedup = (python_elapsed / native_elapsed) if native_elapsed > 0.0 else math.inf
            print(
                f"speedup | steps={steps:>8} | {backend_name}_vs_python={speedup:>8.3f}x"
            )
            divergence = find_first_divergence(
                python_orbit,
                native_orbit,
                limit=min(len(python_orbit.points), len(native_orbit.points)),
            )
            if divergence is None:
                print(f"check   | steps={steps:>8} | {backend_name}: no divergence detected")
            else:
                print_divergence(
                    f"warning | steps={steps:>8} | {backend_name}",
                    divergence,
                )

    print("Batch scan benchmark")
    for seed_count in (100, 1000):
        seeds = make_scan_seeds(seed_count)
        python_elapsed = benchmark_python_scan_dense(
            seeds=seeds,
            steps=1_000,
            repeats=args.repeats,
        )
        native_elapsed = benchmark_native_scan_batch(
            seeds=seeds,
            steps=1_000,
            sample_step=100,
            repeats=args.repeats,
        )
        speedup = (python_elapsed / native_elapsed) if native_elapsed > 0.0 else math.inf
        print(
            f"speedup | seeds={seed_count:>6} | native_batch_vs_python={speedup:>8.3f}x"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
