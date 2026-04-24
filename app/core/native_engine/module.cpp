#include <cmath>
#include <limits>
#include <string>
#include <vector>

#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

namespace py = pybind11;

namespace {

struct PhaseState {
    double d;
    double tau;
    int wall;
};

struct ValidationResult {
    bool valid;
    std::string reason;
};

struct StepResult {
    bool has_state;
    PhaseState state;
    bool valid;
    std::string reason;
};

struct OrbitBuildResult {
    std::vector<int> step_indices;
    std::vector<double> d_values;
    std::vector<double> tau_values;
    std::vector<int> walls;
    int final_step;
    double final_d;
    double final_tau;
    int final_wall;
    bool valid;
    int invalid_step;
    std::string invalid_reason;
};

void add_orbit_result_metadata(py::dict& result, const OrbitBuildResult& orbit_result);

double domain_residual(double d, double tau) {
    return (1.0 - d) * (1.0 - d) + tau * tau - 1.0;
}

double wall_angle(int wall, double alpha, double beta) {
    if (wall == 1) {
        return alpha;
    }
    if (wall == 2) {
        return beta;
    }
    throw std::runtime_error("Unsupported wall index");
}

ValidationResult validate_state(const PhaseState& state, double alpha, double beta, double eps) {
    if (state.wall != 1 && state.wall != 2) {
        return {false, "unsupported_wall"};
    }
    if (state.d <= eps) {
        return {false, "non_positive_d"};
    }
    if (!std::isfinite(state.d) || !std::isfinite(state.tau)) {
        return {false, "non_finite_state"};
    }
    if (!(0.0 < alpha && alpha <= M_PI / 2.0)) {
        return {false, "invalid_alpha"};
    }
    if (!(alpha < beta && beta < M_PI - alpha)) {
        return {false, "invalid_beta"};
    }
    if (domain_residual(state.d, state.tau) >= -eps) {
        return {false, "outside_domain"};
    }
    return {true, ""};
}

int cross_wall_target(int wall) {
    return wall == 1 ? 2 : 1;
}

bool same_wall_allowed(const PhaseState& state, double beta) {
    if (state.wall == 1) {
        return true;
    }
    if (state.wall == 2) {
        return beta >= M_PI / 2.0;
    }
    return false;
}

bool reconstruct_focus(const PhaseState& state, double source_angle, double eps, double& x_coord, double& y_coord) {
    const double sin_2_source = std::sin(2.0 * source_angle);
    if (std::abs(sin_2_source) <= eps || state.d <= eps) {
        return false;
    }

    const double numerator = state.d * std::sin(source_angle) - state.tau * std::cos(source_angle);
    y_coord = 1.0 - ((numerator * numerator) / state.d);
    x_coord = (1.0 + y_coord * std::cos(2.0 * source_angle) - state.d) / sin_2_source;
    return std::isfinite(x_coord) && std::isfinite(y_coord);
}

double compute_cross_wall_d(const PhaseState& state, double source_angle, double target_angle, double eps) {
    double x_coord = 0.0;
    double y_coord = 0.0;
    if (!reconstruct_focus(state, source_angle, eps, x_coord, y_coord)) {
        return std::numeric_limits<double>::quiet_NaN();
    }
    return 1.0 - x_coord * std::sin(2.0 * target_angle) + y_coord * std::cos(2.0 * target_angle);
}

double compute_cross_wall_tau(
    const PhaseState& state,
    double d_next,
    double source_angle,
    double target_angle,
    double eps
) {
    const double cos_target = std::cos(target_angle);
    if (std::abs(cos_target) <= eps || d_next <= eps || state.d <= eps) {
        return std::numeric_limits<double>::quiet_NaN();
    }

    const double numerator = state.d * std::sin(source_angle) - state.tau * std::cos(source_angle);
    const double scale = std::sqrt(d_next / state.d);
    return -d_next * std::tan(target_angle) + (numerator * scale) / cos_target;
}

StepResult next_state_cpp(const PhaseState& state, double alpha, double beta, double eps) {
    const auto validation = validate_state(state, alpha, beta, eps);
    if (!validation.valid) {
        return {false, {}, false, validation.reason};
    }

    const double source_angle = wall_angle(state.wall, alpha, beta);
    const int target_wall = cross_wall_target(state.wall);
    const double target_angle = wall_angle(target_wall, alpha, beta);

    const PhaseState same_wall_state{
        state.d,
        state.tau - 2.0 * state.d * std::tan(source_angle),
        state.wall,
    };
    const auto same_wall_validation = validate_state(same_wall_state, alpha, beta, eps);

    const double d_candidate = compute_cross_wall_d(state, source_angle, target_angle, eps);
    PhaseState cross_wall_state{};
    ValidationResult cross_wall_validation{false, "non_finite_cross_wall"};
    if (std::isfinite(d_candidate)) {
        const double tau_candidate = compute_cross_wall_tau(state, d_candidate, source_angle, target_angle, eps);
        if (std::isfinite(tau_candidate)) {
            cross_wall_state = {d_candidate, tau_candidate, target_wall};
            cross_wall_validation = validate_state(cross_wall_state, alpha, beta, eps);
        } else {
            cross_wall_validation = {false, "non_finite_cross_wall_tau"};
        }
    }

    PhaseState next_phase_state{};
    if (cross_wall_validation.valid) {
        next_phase_state = cross_wall_state;
    } else if (same_wall_allowed(state, beta) && same_wall_validation.valid) {
        next_phase_state = same_wall_state;
    } else {
        if (!std::isfinite(d_candidate)) {
            return {false, {}, false, cross_wall_validation.reason};
        }
        next_phase_state = cross_wall_state;
    }

    const auto next_validation = validate_state(next_phase_state, alpha, beta, eps);
    if (!next_validation.valid) {
        return {true, next_phase_state, false, next_validation.reason};
    }

    return {true, next_phase_state, true, ""};
}

OrbitBuildResult build_native_orbit_result(
    double d0,
    double tau0,
    int wall0,
    double alpha,
    double beta,
    int steps,
    int sample_step,
    const std::string& sample_mode
) {
    constexpr double eps = 1.0e-9;
    const std::string normalized_mode = sample_mode == "dense" ? "dense" : sample_mode;
    const int normalized_step = sample_step <= 1 ? 1 : sample_step;
    if (
        normalized_mode != "dense" &&
        normalized_mode != "every_n" &&
        normalized_mode != "final"
    ) {
        throw std::runtime_error("Unsupported sample_mode");
    }

    OrbitBuildResult result{
        {},
        {},
        {},
        {},
        0,
        d0,
        tau0,
        wall0,
        true,
        -1,
        "",
    };
    if (normalized_mode != "final" && steps > 0) {
        result.step_indices.reserve(static_cast<size_t>(steps));
        result.d_values.reserve(static_cast<size_t>(steps));
        result.tau_values.reserve(static_cast<size_t>(steps));
        result.walls.reserve(static_cast<size_t>(steps));
    }

    PhaseState current_state{d0, tau0, wall0};
    const auto initial_validation = validate_state(current_state, alpha, beta, eps);
    if (normalized_mode == "dense" || normalized_mode == "every_n") {
        result.step_indices.push_back(0);
        result.d_values.push_back(current_state.d);
        result.tau_values.push_back(current_state.tau);
        result.walls.push_back(current_state.wall);
    }

    result.valid = initial_validation.valid;
    result.invalid_reason = initial_validation.reason;
    if (result.valid && steps > 1) {
        for (int step_index = 1; step_index < steps; ++step_index) {
            const auto step_result = next_state_cpp(current_state, alpha, beta, eps);
            if (!step_result.has_state) {
                result.valid = false;
                result.invalid_step = step_index;
                result.invalid_reason = step_result.reason;
                break;
            }

            result.final_step = step_index;
            result.final_d = step_result.state.d;
            result.final_tau = step_result.state.tau;
            result.final_wall = step_result.state.wall;

            const bool should_sample =
                normalized_mode == "dense" ||
                (normalized_mode == "every_n" && (step_index % normalized_step) == 0);
            if (should_sample) {
                result.step_indices.push_back(step_index);
                result.d_values.push_back(step_result.state.d);
                result.tau_values.push_back(step_result.state.tau);
                result.walls.push_back(step_result.state.wall);
            }

            if (!step_result.valid) {
                result.valid = false;
                result.invalid_step = step_index;
                result.invalid_reason = step_result.reason;
                break;
            }
            current_state = step_result.state;
        }
    }

    if (!result.valid && result.invalid_reason.empty()) {
        result.invalid_reason = initial_validation.reason;
    }

    if (normalized_mode == "final") {
        result.step_indices.push_back(result.final_step);
        result.d_values.push_back(result.final_d);
        result.tau_values.push_back(result.final_tau);
        result.walls.push_back(result.final_wall);
    } else if (
        !result.step_indices.empty() &&
        (
            result.step_indices.back() != result.final_step ||
            result.d_values.back() != result.final_d ||
            result.tau_values.back() != result.final_tau ||
            result.walls.back() != result.final_wall
        )
    ) {
        result.step_indices.push_back(result.final_step);
        result.d_values.push_back(result.final_d);
        result.tau_values.push_back(result.final_tau);
        result.walls.push_back(result.final_wall);
    }

    return result;
}

py::dict dense_result_to_python_dict(const OrbitBuildResult& dense) {
    const auto size = static_cast<py::ssize_t>(dense.step_indices.size());
    py::array_t<int> step_array(size);
    py::array_t<double> d_array(size);
    py::array_t<double> tau_array(size);
    py::array_t<int> wall_array(size);
    auto step_view = step_array.mutable_unchecked<1>();
    auto d_view = d_array.mutable_unchecked<1>();
    auto tau_view = tau_array.mutable_unchecked<1>();
    auto wall_view = wall_array.mutable_unchecked<1>();
    for (py::ssize_t i = 0; i < size; ++i) {
        step_view(i) = dense.step_indices[static_cast<size_t>(i)];
        d_view(i) = dense.d_values[static_cast<size_t>(i)];
        tau_view(i) = dense.tau_values[static_cast<size_t>(i)];
        wall_view(i) = dense.walls[static_cast<size_t>(i)];
    }

    py::dict result;
    result["steps"] = std::move(step_array);
    result["d"] = std::move(d_array);
    result["tau"] = std::move(tau_array);
    result["wall"] = std::move(wall_array);
    add_orbit_result_metadata(result, dense);
    return result;
}

void add_orbit_result_metadata(py::dict& result, const OrbitBuildResult& orbit_result) {
    result["final_step"] = py::int_(orbit_result.final_step);
    result["final_d"] = py::float_(orbit_result.final_d);
    result["final_tau"] = py::float_(orbit_result.final_tau);
    result["final_wall"] = py::int_(orbit_result.final_wall);
    result["valid"] = py::bool_(orbit_result.valid);
    if (orbit_result.invalid_step < 0) {
        result["invalid_step"] = py::none();
    } else {
        result["invalid_step"] = py::int_(orbit_result.invalid_step);
    }
    if (orbit_result.valid) {
        result["invalid_reason"] = py::none();
    } else {
        result["invalid_reason"] = py::str(orbit_result.invalid_reason);
    }
}

py::dict native_build_dense_orbit_impl(
    double d0,
    double tau0,
    int wall0,
    double alpha,
    double beta,
    int steps
) {
    return dense_result_to_python_dict(
        build_native_orbit_result(d0, tau0, wall0, alpha, beta, steps, 1, "dense")
    );
}

py::dict native_build_sparse_orbit_impl(
    double d0,
    double tau0,
    int wall0,
    double alpha,
    double beta,
    int steps,
    int sample_step,
    const std::string& sample_mode
) {
    const auto result_data = build_native_orbit_result(
        d0,
        tau0,
        wall0,
        alpha,
        beta,
        steps,
        sample_step,
        sample_mode
    );

    const auto size = static_cast<py::ssize_t>(result_data.step_indices.size());
    py::array_t<int> step_array(size);
    py::array_t<double> d_array(size);
    py::array_t<double> tau_array(size);
    py::array_t<int> wall_array(size);
    auto step_view = step_array.mutable_unchecked<1>();
    auto d_view = d_array.mutable_unchecked<1>();
    auto tau_view = tau_array.mutable_unchecked<1>();
    auto wall_view = wall_array.mutable_unchecked<1>();
    for (py::ssize_t i = 0; i < size; ++i) {
        step_view(i) = result_data.step_indices[static_cast<size_t>(i)];
        d_view(i) = result_data.d_values[static_cast<size_t>(i)];
        tau_view(i) = result_data.tau_values[static_cast<size_t>(i)];
        wall_view(i) = result_data.walls[static_cast<size_t>(i)];
    }

    py::dict result;
    result["steps"] = std::move(step_array);
    result["d"] = std::move(d_array);
    result["tau"] = std::move(tau_array);
    result["wall"] = std::move(wall_array);
    add_orbit_result_metadata(result, result_data);
    return result;
}

py::list native_build_sparse_orbits_batch_impl(
    py::array_t<double, py::array::c_style | py::array::forcecast> d0_list,
    py::array_t<double, py::array::c_style | py::array::forcecast> tau0_list,
    py::array_t<int, py::array::c_style | py::array::forcecast> wall0_list,
    double alpha,
    double beta,
    int steps,
    int sample_step,
    const std::string& sample_mode
) {
    const auto d0_view = d0_list.unchecked<1>();
    const auto tau0_view = tau0_list.unchecked<1>();
    const auto wall0_view = wall0_list.unchecked<1>();
    if (d0_view.shape(0) != tau0_view.shape(0) || d0_view.shape(0) != wall0_view.shape(0)) {
        throw std::runtime_error("batch input arrays must have matching lengths");
    }

    py::list batch_results;
    for (py::ssize_t seed_index = 0; seed_index < d0_view.shape(0); ++seed_index) {
        const auto orbit_result = build_native_orbit_result(
            d0_view(seed_index),
            tau0_view(seed_index),
            wall0_view(seed_index),
            alpha,
            beta,
            steps,
            sample_step,
            sample_mode
        );

        const auto size = static_cast<py::ssize_t>(orbit_result.step_indices.size());
        py::array_t<int> step_array(size);
        py::array_t<double> d_array(size);
        py::array_t<double> tau_array(size);
        py::array_t<int> wall_array(size);
        auto step_view = step_array.mutable_unchecked<1>();
        auto d_view = d_array.mutable_unchecked<1>();
        auto tau_view = tau_array.mutable_unchecked<1>();
        auto wall_view = wall_array.mutable_unchecked<1>();
        for (py::ssize_t i = 0; i < size; ++i) {
            step_view(i) = orbit_result.step_indices[static_cast<size_t>(i)];
            d_view(i) = orbit_result.d_values[static_cast<size_t>(i)];
            tau_view(i) = orbit_result.tau_values[static_cast<size_t>(i)];
            wall_view(i) = orbit_result.walls[static_cast<size_t>(i)];
        }

        py::dict result;
        result["steps"] = std::move(step_array);
        result["d"] = std::move(d_array);
        result["tau"] = std::move(tau_array);
        result["wall"] = std::move(wall_array);
        add_orbit_result_metadata(result, orbit_result);
        batch_results.append(std::move(result));
    }
    return batch_results;
}

}  // namespace

PYBIND11_MODULE(_native_engine, m) {
    m.doc() = "Minimal native backend scaffold for wedge.";
    m.def("native_backend_available", []() { return true; });
    m.def("add_ints", [](int a, int b) { return a + b; });
    m.def(
        "native_build_dense_orbit",
        &native_build_dense_orbit_impl,
        py::arg("d0"),
        py::arg("tau0"),
        py::arg("wall0"),
        py::arg("alpha"),
        py::arg("beta"),
        py::arg("steps")
    );
    m.def(
        "native_build_sparse_orbit",
        &native_build_sparse_orbit_impl,
        py::arg("d0"),
        py::arg("tau0"),
        py::arg("wall0"),
        py::arg("alpha"),
        py::arg("beta"),
        py::arg("steps"),
        py::arg("sample_step"),
        py::arg("sample_mode")
    );
    m.def(
        "native_build_sparse_orbits_batch",
        &native_build_sparse_orbits_batch_impl,
        py::arg("d0_list"),
        py::arg("tau0_list"),
        py::arg("wall0_list"),
        py::arg("alpha"),
        py::arg("beta"),
        py::arg("steps"),
        py::arg("sample_step"),
        py::arg("sample_mode")
    );
}
