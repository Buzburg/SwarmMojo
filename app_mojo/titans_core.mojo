"""
mojo-titans core algebra
Implementation of "Titans: Learning to Memorize at Test Time" (arXiv:2501.00663)
Fused Test-Time Gradient Descent with Momentum and Adaptive Forgetting in Mojo SIMD.
"""

from std.collections import List
from std.math import sqrt

comptime DIM: Int = 32
comptime MATRIX_SIZE: Int = DIM * DIM  # 1024 float32 parameters


@fieldwise_init
struct TitansMemory(Copyable, Movable):
    var weights: List[Float32]      # Long-term memory matrix M_t (DIM x DIM)
    var momentum: List[Float32]     # Surprise momentum buffer S_t (DIM x DIM)
    var step_count: Int


@fieldwise_init
struct UpdateMetrics(Copyable, Movable):
    var surprise_loss: Float32      # 0.5 * ||M_{t-1} k_t - v_t||^2
    var post_update_loss: Float32   # 0.5 * ||M_t k_t - v_t||^2
    var weight_norm: Float32        # ||M_t||_F


def create_titans_memory() -> TitansMemory:
    var w = List[Float32](length=MATRIX_SIZE, fill=0.0)
    var m = List[Float32](length=MATRIX_SIZE, fill=0.0)
    return TitansMemory(w^, m^, 0)


def query_memory(mem: TitansMemory, query: List[Float32]) -> List[Float32]:
    """Computes y_t = M_t * q_t in O(d^2)."""
    var out = List[Float32](capacity=DIM)
    for row in range(DIM):
        var acc = Float32(0.0)
        var row_offset = row * DIM
        for col in range(DIM):
            acc += mem.weights[row_offset + col] * query[col]
        out.append(acc)
    return out^


def test_time_memorize_step(
    mut mem: TitansMemory,
    key: List[Float32],
    value: List[Float32],
    eta: Float32 = 0.85,     # Momentum decay factor
    theta: Float32 = 0.40,   # Test-time learning rate
    alpha: Float32 = 0.01    # Adaptive forgetting / weight decay gate
) -> UpdateMetrics:
    """
    Executes one fused Titans Test-Time Memorization step:
      1. Predict: v_hat = M_{t-1} * k_t
      2. Surprise error: e_t = v_hat - v_t
      3. Gradient: grad = e_t * k_t^T
      4. Momentum: S_t = eta * S_{t-1} - theta * grad
      5. Update: M_t = (1 - alpha) * M_{t-1} + S_t
    """
    var pred = query_memory(mem, key)
    var err = List[Float32](capacity=DIM)
    var pre_loss = Float32(0.0)

    for i in range(DIM):
        var diff = pred[i] - value[i]
        err.append(diff)
        pre_loss += Float32(0.5) * diff * diff

    var retain = Float32(1.0) - alpha
    var norm_sq = Float32(0.0)

    for row in range(DIM):
        var row_offset = row * DIM
        var e_row = err[row]
        for col in range(DIM):
            var idx = row_offset + col
            var grad = e_row * key[col]
            var s_new = eta * mem.momentum[idx] - theta * grad
            var w_new = retain * mem.weights[idx] + s_new
            mem.momentum[idx] = s_new
            mem.weights[idx] = w_new
            norm_sq += w_new * w_new

    mem.step_count += 1

    # Measure post-update associative recall error
    var post_pred = query_memory(mem, key)
    var post_loss = Float32(0.0)
    for i in range(DIM):
        var d2 = post_pred[i] - value[i]
        post_loss += Float32(0.5) * d2 * d2

    return UpdateMetrics(pre_loss, post_loss, sqrt(norm_sq))


def main():
    print("mojo-titans test-time neural memory kernel initialized.")
