import numpy as np
import hashlib


# ---------- вспомогательная функция ----------
def _coord_seed(coords) -> int:
    """Преобразует массив координат в 64-битовый сид (через SHA-256)."""
    arr = np.asarray(coords)
    if arr.ndim == 0:               # скаляр → (1,)
        arr = arr.reshape(1)

    # целые / float → единый формат uint64
    if arr.dtype.kind in "iu":
        data = arr.astype(np.uint64).tobytes()
    else:
        data = arr.astype(np.float64).view(np.uint64).tobytes()

    digest = hashlib.sha256(data).digest()[:8]
    return int.from_bytes(digest, "little")


# ---------- основной генератор ----------
def noise(
    coords,
    size=None,
    distribution="uniform",
    *,
    seed=None,
    low=None,
    high=None,
    mean=0.0,
    std=1.0,
    dtype=np.int64,
    endpoint=False,
):
    """
    Генерирует детерминированный шум.

    coords : array-like
        N-мерный массив координат.
    size : int | tuple | None
        Размер результата (по умолчанию — shape(coords)).
    distribution : {"uniform", "normal", "int"}
        Тип распределения.
    seed : int | str | bytes | None
        Дополнительный сид.  Позволяет получать разные значения
        при тех же координатах.  Если None — зависит только от coords.
    low, high : float | int | None
        Диапазон для "uniform" и "int".
    mean, std : float
        Параметры нормального распределения.
    dtype, endpoint
        Параметры для "int" (соответствуют NumPy).
    """
    coords_arr = np.asarray(coords)
    if size is None:
        size = coords_arr.shape

    base_seed = _coord_seed(coords_arr)

    # --- смешиваем с пользовательским сидом, если он есть ---
    if seed is None:
        final_seed = base_seed
    else:
        # превращаем seed в bytes
        if isinstance(seed, (bytes, bytearray)):
            seed_bytes = bytes(seed)
        elif isinstance(seed, str):
            seed_bytes = seed.encode()
        else:  # предполагаем целое
            seed_int = int(seed) & ((1 << 64) - 1)
            seed_bytes = seed_int.to_bytes(8, "little", signed=False)

        mixed = hashlib.sha256(base_seed.to_bytes(8, "little") + seed_bytes).digest()[:8]
        final_seed = int.from_bytes(mixed, "little")

    rng = np.random.Generator(np.random.PCG64(final_seed))

    # --- выдаём распределение ---
    if distribution == "uniform":
        low = 0.0 if low is None else low
        high = 1.0 if high is None else high
        return rng.uniform(low, high, size)

    elif distribution == "normal":
        return rng.normal(mean, std, size)

    elif distribution == "int":
        if low is None and high is None:
            low, high = 0, 2**64
        elif low is None or high is None:
            raise ValueError("Для 'int' укажите оба параметра: low и high")
        return rng.integers(low, high, size, dtype=dtype, endpoint=endpoint)

    else:
        raise ValueError(f"Unknown distribution: {distribution}")


if __name__ == "__main__":
    # 1. Равномерный шум в диапазоне [-1, 1) для 3-D точки
    print(noise([1546.0, 97.0, 36.0], distribution="int", seed=65665534, low=0, high=1))

    # 1. Стандартное поведение (только координаты)
    print("A:", noise([1546.0, 97.0, 36.0]))

    # 2. Тот же ввод + seed=42 → другое значение
    print("B:", noise([1546.0, 97.0, 36.0], seed=42))

    # 3. Тот же ввод + seed=42 ещё раз  → совпадает с B
    print("C:", noise([1546.0, 97.0, 36.0], seed=42))

    # 4. Другой сид
    print("D:", noise([1546.0, 97.0, 36.0], seed="custom-run"))

    # 2. Целочисленный шум от 10 до 20 (включительно 19) для 2×2 матрицы координат
    coords = [[0, 1],
          [2, 3]]
    print(noise(coords, distribution="int", low=10, high=20))

    # 3. Нормальное распределение N(10, 2) для 5-элементного вектора координат
    print(noise([5, 5, 5, 5, 5], distribution="normal", mean=10, std=2))

