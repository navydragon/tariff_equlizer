from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from decimal import Decimal
from itertools import permutations

import numpy as np

from calculations.domain.constants import GROUP_BY_CHOICES, EFFECTS_GROUP_BY_CHOICES
from calculations.domain.services.scenario_effects_compact import (
    _COMPUTE_DTYPE,
    _DIMENSION_COLUMNS,
    _FLOAT_DTYPE,
    prepare_compact_inputs,
)

DENSE_PAIR_MAX_CELLS = 1_048_576
DENSE_TRIPLE_MAX_CELLS = 1_048_576
SMALL_PAIR_MAX_CELLS = 65_536
FILTER_OUTER = "cargo_group"
FILTER_INNER = "holding"
SKIP_PAIR_KEYS = frozenset({("cargo_code", "cargo_code")})


def _should_build_pair(outer: str, inner: str, n_outer: int, n_inner: int) -> bool:
    if (outer, inner) in SKIP_PAIR_KEYS:
        return False
    n_cells = n_outer * n_inner
    if n_cells > DENSE_PAIR_MAX_CELLS:
        return False
    if n_cells <= SMALL_PAIR_MAX_CELLS:
        return True
    if outer in EFFECTS_GROUP_BY_CHOICES or inner in EFFECTS_GROUP_BY_CHOICES:
        return True
    if FILTER_OUTER in {outer, inner} or FILTER_INNER in {outer, inner}:
        return True
    if "cargo_code" in {outer, inner}:
        return True
    return False


def _should_build_filter_triple(n_a: int, n_b: int, n_c: int) -> bool:
    return n_a * n_b * n_c <= DENSE_TRIPLE_MAX_CELLS


def _pair_worker_count(n_pairs: int) -> int:
    if n_pairs <= 1:
        return 1
    return min(8, n_pairs)


@dataclass
class SingleBucket:
    base: np.ndarray
    rules: np.ndarray
    charge: np.ndarray
    volume: np.ndarray


@dataclass
class DensePairBucket:
    outer_dim: str
    inner_dim: str
    n_outer: int
    n_inner: int
    base: np.ndarray
    rules: np.ndarray
    charge: np.ndarray
    volume: np.ndarray


@dataclass
class SparsePairBucket:
    outer_dim: str
    inner_dim: str
    n_outer: int
    n_inner: int
    outer_idx: np.ndarray
    inner_idx: np.ndarray
    base: np.ndarray
    rules: np.ndarray
    charge: np.ndarray
    volume: np.ndarray


@dataclass
class DenseTripleBucket:
    dim_a: str
    dim_b: str
    dim_c: str
    shape: tuple[int, int, int]
    base: np.ndarray
    rules: np.ndarray
    charge: np.ndarray
    volume: np.ndarray


@dataclass
class SparseTripleBucket:
    dim_a: str
    dim_b: str
    dim_c: str
    shape: tuple[int, int, int]
    flat_idx: np.ndarray
    base: np.ndarray
    rules: np.ndarray
    charge: np.ndarray
    volume: np.ndarray


@dataclass(frozen=True)
class EffectsPreAggregate:
    years: list[int]
    dimension_labels: dict[str, list[str]]
    singles: dict[str, SingleBucket]
    pairs_dense: dict[tuple[str, str], DensePairBucket]
    pairs_sparse: dict[tuple[str, str], SparsePairBucket]
    triples_dense: dict[tuple[str, str, str], DenseTripleBucket] = field(
        default_factory=dict,
    )
    triples_sparse: dict[tuple[str, str, str], SparseTripleBucket] = field(
        default_factory=dict,
    )


def _label_for_code(preagg: EffectsPreAggregate, dimension: str, code: int) -> str:
    labels = preagg.dimension_labels.get(dimension, [])
    if 0 <= code < len(labels):
        return labels[code]
    return "—"


def _allowed_indices(
    labels: list[str],
    selected: list[str] | None,
) -> np.ndarray | None:
    if not selected:
        return None
    allowed = {idx for idx, label in enumerate(labels) if label in selected}
    if not allowed:
        return np.array([], dtype=np.int32)
    return np.array(sorted(allowed), dtype=np.int32)


class EffectsPreAggregateBuilder:
    def __init__(
        self,
        *,
        years: list[int],
        dimension_labels: dict[str, list[str]],
        dim_codes: dict[str, np.ndarray],
        volume: np.ndarray,
    ) -> None:
        self.years = years
        self.n_years = len(years)
        self.dimension_labels = dimension_labels
        self.dim_codes = dim_codes
        self.volume = volume.astype(_COMPUTE_DTYPE, copy=False)

        self.singles: dict[str, SingleBucket] = {}
        for dim in _DIMENSION_COLUMNS:
            if dim not in dim_codes:
                continue
            n_groups = len(dimension_labels.get(dim, [])) or int(dim_codes[dim].max()) + 1
            self.singles[dim] = SingleBucket(
                base=np.zeros((n_groups, self.n_years), dtype=_FLOAT_DTYPE),
                rules=np.zeros((n_groups, self.n_years), dtype=_FLOAT_DTYPE),
                charge=np.zeros((n_groups, self.n_years), dtype=_FLOAT_DTYPE),
                volume=np.zeros(n_groups, dtype=_FLOAT_DTYPE),
            )

        self.pairs_dense: dict[tuple[str, str], DensePairBucket] = {}
        self.pairs_sparse: dict[tuple[str, str], SparsePairBucket] = {}

        self.triples_dense: dict[tuple[str, str, str], DenseTripleBucket] = {}
        self.triples_sparse: dict[tuple[str, str, str], SparseTripleBucket] = {}

        self._init_pairs()
        self._init_filter_triples()
        self._accumulate_volumes_to_pairs_and_triples()

        np.add.at(
            self.singles[FILTER_OUTER].volume,
            dim_codes[FILTER_OUTER],
            self.volume,
        )
        np.add.at(
            self.singles[FILTER_INNER].volume,
            dim_codes[FILTER_INNER],
            self.volume,
        )
        for dim in self.singles:
            if dim in {FILTER_OUTER, FILTER_INNER}:
                continue
            np.add.at(self.singles[dim].volume, dim_codes[dim], self.volume)

    def _init_pairs(self) -> None:
        for outer, inner in permutations(GROUP_BY_CHOICES, 2):
            n_outer = len(self.dimension_labels.get(outer, []))
            n_inner = len(self.dimension_labels.get(inner, []))
            if n_outer == 0 or n_inner == 0:
                continue
            if not _should_build_pair(outer, inner, n_outer, n_inner):
                continue
            key = (outer, inner)
            self.pairs_dense[key] = DensePairBucket(
                outer_dim=outer,
                inner_dim=inner,
                n_outer=n_outer,
                n_inner=n_inner,
                base=np.zeros((n_outer, n_inner, self.n_years), dtype=_FLOAT_DTYPE),
                rules=np.zeros((n_outer, n_inner, self.n_years), dtype=_FLOAT_DTYPE),
                charge=np.zeros((n_outer, n_inner, self.n_years), dtype=_FLOAT_DTYPE),
                volume=np.zeros((n_outer, n_inner), dtype=_FLOAT_DTYPE),
            )

    def _init_filter_triples(self) -> None:
        for third in GROUP_BY_CHOICES:
            if third in {FILTER_OUTER, FILTER_INNER}:
                continue
            key = (FILTER_OUTER, FILTER_INNER, third)
            n_a = len(self.dimension_labels.get(FILTER_OUTER, []))
            n_b = len(self.dimension_labels.get(FILTER_INNER, []))
            n_c = len(self.dimension_labels.get(third, []))
            if n_a == 0 or n_b == 0 or n_c == 0:
                continue
            if not _should_build_filter_triple(n_a, n_b, n_c):
                continue
            self.triples_dense[key] = DenseTripleBucket(
                dim_a=FILTER_OUTER,
                dim_b=FILTER_INNER,
                dim_c=third,
                shape=(n_a, n_b, n_c),
                base=np.zeros((n_a, n_b, n_c, self.n_years), dtype=_FLOAT_DTYPE),
                rules=np.zeros((n_a, n_b, n_c, self.n_years), dtype=_FLOAT_DTYPE),
                charge=np.zeros((n_a, n_b, n_c, self.n_years), dtype=_FLOAT_DTYPE),
                volume=np.zeros((n_a, n_b, n_c), dtype=_FLOAT_DTYPE),
            )

    def _accumulate_volumes_to_pairs_and_triples(self) -> None:
        pair_keys = list(self.pairs_dense.keys())
        if not pair_keys:
            return
        workers = _pair_worker_count(len(pair_keys))

        def _accumulate_pair_volume(key: tuple[str, str]) -> None:
            bucket = self.pairs_dense[key]
            outer_codes = self.dim_codes[bucket.outer_dim]
            inner_codes = self.dim_codes[bucket.inner_dim]
            np.add.at(bucket.volume, (outer_codes, inner_codes), self.volume)

        if workers == 1:
            for key in pair_keys:
                _accumulate_pair_volume(key)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                list(executor.map(_accumulate_pair_volume, pair_keys))

        triple_keys = list(self.triples_dense.keys())
        if not triple_keys:
            return
        workers = _pair_worker_count(len(triple_keys))

        def _accumulate_triple_volume(key: tuple[str, str, str]) -> None:
            bucket = self.triples_dense[key]
            a_codes = self.dim_codes[bucket.dim_a]
            b_codes = self.dim_codes[bucket.dim_b]
            c_codes = self.dim_codes[bucket.dim_c]
            np.add.at(bucket.volume, (a_codes, b_codes, c_codes), self.volume)

        if workers == 1:
            for key in triple_keys:
                _accumulate_triple_volume(key)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                list(executor.map(_accumulate_triple_volume, triple_keys))

    def _accumulate_single(
        self,
        dim: str,
        *,
        year_index: int,
        base_inc: np.ndarray,
        rules_inc: np.ndarray,
        charge_vals: np.ndarray,
    ) -> None:
        bucket = self.singles.get(dim)
        if bucket is None:
            return
        codes = self.dim_codes[dim]
        np.add.at(bucket.base[:, year_index], codes, base_inc)
        np.add.at(bucket.rules[:, year_index], codes, rules_inc)
        np.add.at(bucket.charge[:, year_index], codes, charge_vals)

    def _accumulate_dense_pair(
        self,
        key: tuple[str, str],
        *,
        year_index: int,
        base_inc: np.ndarray,
        rules_inc: np.ndarray,
        charge_vals: np.ndarray,
    ) -> None:
        bucket = self.pairs_dense[key]
        outer_codes = self.dim_codes[bucket.outer_dim]
        inner_codes = self.dim_codes[bucket.inner_dim]
        np.add.at(bucket.base[:, :, year_index], (outer_codes, inner_codes), base_inc)
        np.add.at(bucket.rules[:, :, year_index], (outer_codes, inner_codes), rules_inc)
        np.add.at(bucket.charge[:, :, year_index], (outer_codes, inner_codes), charge_vals)

    def _accumulate_dense_triple(
        self,
        key: tuple[str, str, str],
        *,
        year_index: int,
        base_inc: np.ndarray,
        rules_inc: np.ndarray,
        charge_vals: np.ndarray,
    ) -> None:
        bucket = self.triples_dense[key]
        a_codes = self.dim_codes[bucket.dim_a]
        b_codes = self.dim_codes[bucket.dim_b]
        c_codes = self.dim_codes[bucket.dim_c]
        np.add.at(bucket.base[:, :, :, year_index], (a_codes, b_codes, c_codes), base_inc)
        np.add.at(bucket.rules[:, :, :, year_index], (a_codes, b_codes, c_codes), rules_inc)
        np.add.at(bucket.charge[:, :, :, year_index], (a_codes, b_codes, c_codes), charge_vals)

    def accumulate_year(
        self,
        *,
        year_index: int,
        base_inc: np.ndarray,
        rules_inc: np.ndarray,
        charge_vals: np.ndarray,
    ) -> None:
        for dim in self.singles:
            self._accumulate_single(
                dim,
                year_index=year_index,
                base_inc=base_inc,
                rules_inc=rules_inc,
                charge_vals=charge_vals,
            )

        pair_keys = list(self.pairs_dense.keys())
        triple_keys = list(self.triples_dense.keys())
        workers = _pair_worker_count(len(pair_keys) + len(triple_keys))

        def _accumulate_pair(key: tuple[str, str]) -> None:
            self._accumulate_dense_pair(
                key,
                year_index=year_index,
                base_inc=base_inc,
                rules_inc=rules_inc,
                charge_vals=charge_vals,
            )

        def _accumulate_triple(key: tuple[str, str, str]) -> None:
            self._accumulate_dense_triple(
                key,
                year_index=year_index,
                base_inc=base_inc,
                rules_inc=rules_inc,
                charge_vals=charge_vals,
            )

        if workers == 1:
            for key in pair_keys:
                _accumulate_pair(key)
            for key in triple_keys:
                _accumulate_triple(key)
        else:
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(_accumulate_pair, key)
                    for key in pair_keys
                ]
                futures.extend(
                    executor.submit(_accumulate_triple, key)
                    for key in triple_keys
                )
                for future in futures:
                    future.result()

    def accumulate_initial_charge(self, *, charge_vals: np.ndarray) -> None:
        self.accumulate_year(
            year_index=0,
            base_inc=np.zeros_like(charge_vals),
            rules_inc=np.zeros_like(charge_vals),
            charge_vals=charge_vals,
        )

    def finalize(self) -> EffectsPreAggregate:
        return EffectsPreAggregate(
            years=self.years,
            dimension_labels=self.dimension_labels,
            singles=self.singles,
            pairs_dense=self.pairs_dense,
            pairs_sparse=self.pairs_sparse,
            triples_dense=self.triples_dense,
            triples_sparse=self.triples_sparse,
        )


def build_preaggregate_builder(
    df,
    *,
    years: list[int],
    mart_meta,
) -> EffectsPreAggregateBuilder | None:
    dimensions, dimension_labels, volume = prepare_compact_inputs(df, mart_meta)
    if not dimensions:
        return None
    return EffectsPreAggregateBuilder(
        years=years,
        dimension_labels=dimension_labels,
        dim_codes=dimensions,
        volume=volume,
    )


def _read_metric_array(
    array: np.ndarray,
    *,
    metric: str,
    year_index: int,
    prev_year_index: int,
) -> np.ndarray:
    if metric == "volume":
        return array
    if metric == "prev_charge":
        year_index = prev_year_index
    if array.ndim == 1:
        return array
    if array.ndim == 2:
        return array[:, year_index]
    if array.ndim == 3:
        return array[:, :, year_index]
    return array[:, :, :, year_index]


def _group_sums(
    preagg: EffectsPreAggregate,
    *,
    group_by: str,
    group_by_inner: str,
    cargo_groups: list[str],
    holdings: list[str],
    metric: str,
    year_index: int,
    prev_year_index: int,
) -> dict[tuple[int, int | None], float]:
    outer = group_by if group_by in GROUP_BY_CHOICES else FILTER_OUTER
    inner = None if group_by_inner == "none" else group_by_inner
    cargo_allowed = _allowed_indices(
        preagg.dimension_labels.get(FILTER_OUTER, []),
        cargo_groups or None,
    )
    holding_allowed = _allowed_indices(
        preagg.dimension_labels.get(FILTER_INNER, []),
        holdings or None,
    )

    result: dict[tuple[int, int | None], float] = {}

    def _from_single(dim: str) -> None:
        bucket = preagg.singles[dim]
        values = _read_metric_array(
            bucket.base if metric == "base"
            else bucket.rules if metric == "rules"
            else bucket.charge if metric in {"charge", "prev_charge"}
            else bucket.volume,
            metric=metric,
            year_index=year_index,
            prev_year_index=prev_year_index,
        )
        if dim == FILTER_OUTER and cargo_allowed is not None:
            indices = cargo_allowed
        elif dim == FILTER_INNER and holding_allowed is not None:
            indices = holding_allowed
        else:
            indices = np.arange(len(values), dtype=np.int32)
        for code in indices:
            val = float(values[int(code)])
            if val:
                result[(int(code), None)] = val

    def _from_dense_pair(key: tuple[str, str], *, sum_outer: bool) -> None:
        bucket = preagg.pairs_dense[key]
        values = _read_metric_array(
            bucket.base if metric == "base"
            else bucket.rules if metric == "rules"
            else bucket.charge if metric in {"charge", "prev_charge"}
            else bucket.volume,
            metric=metric,
            year_index=year_index,
            prev_year_index=prev_year_index,
        )
        outer_dim, inner_dim = key
        cargo_axis = 0 if outer_dim == FILTER_OUTER else (1 if inner_dim == FILTER_OUTER else None)
        holding_axis = 0 if outer_dim == FILTER_INNER else (1 if inner_dim == FILTER_INNER else None)

        if cargo_axis is not None and cargo_allowed is not None:
            values = np.take(values, cargo_allowed, axis=cargo_axis)
        if holding_axis is not None and holding_allowed is not None:
            values = np.take(values, holding_allowed, axis=holding_axis)

        if inner is None:
            target_dim = outer
            if bucket.outer_dim == target_dim:
                collapsed = values.sum(axis=1, dtype=np.float64)
                for code, val in enumerate(collapsed):
                    if val:
                        result[(int(code), None)] = float(val)
            else:
                collapsed = values.sum(axis=0, dtype=np.float64)
                for code, val in enumerate(collapsed):
                    if val:
                        result[(int(code), None)] = float(val)
            return

        if bucket.outer_dim == outer and bucket.inner_dim == inner:
            for o in range(values.shape[0]):
                for i in range(values.shape[1]):
                    val = float(values[o, i])
                    if val:
                        result[(int(o), int(i))] = val
            if sum_outer:
                for o in range(values.shape[0]):
                    total = float(values[o, :].sum(dtype=np.float64))
                    if total:
                        result[(int(o), None)] = total

    def _from_sparse_pair(key: tuple[str, str]) -> None:
        bucket = preagg.pairs_sparse[key]
        for idx in range(len(bucket.outer_idx)):
            o = int(bucket.outer_idx[idx])
            i = int(bucket.inner_idx[idx])
            if cargo_allowed is not None:
                if bucket.outer_dim == FILTER_OUTER and o not in set(cargo_allowed):
                    continue
                if bucket.inner_dim == FILTER_OUTER and i not in set(cargo_allowed):
                    continue
            if holding_allowed is not None:
                if bucket.outer_dim == FILTER_INNER and o not in set(holding_allowed):
                    continue
                if bucket.inner_dim == FILTER_INNER and i not in set(holding_allowed):
                    continue
            if metric == "volume":
                val = float(bucket.volume[idx])
            elif metric == "base":
                val = float(bucket.base[idx, year_index])
            elif metric == "rules":
                val = float(bucket.rules[idx, year_index])
            elif metric == "charge":
                val = float(bucket.charge[idx, year_index])
            else:
                val = float(bucket.charge[idx, prev_year_index])
            if not val:
                continue
            if bucket.outer_dim == outer and bucket.inner_dim == (inner or bucket.inner_dim):
                result[(o, i if inner else None)] = result.get((o, i if inner else None), 0.0) + val
            elif bucket.outer_dim == outer:
                result[(o, None if inner is None else i)] = (
                    result.get((o, None if inner is None else i), 0.0) + val
                )

    def _from_dense_triple(key: tuple[str, str, str]) -> None:
        bucket = preagg.triples_dense[key]
        values = _read_metric_array(
            bucket.base if metric == "base"
            else bucket.rules if metric == "rules"
            else bucket.charge if metric in {"charge", "prev_charge"}
            else bucket.volume,
            metric=metric,
            year_index=year_index,
            prev_year_index=prev_year_index,
        )
        if cargo_allowed is not None:
            values = np.take(values, cargo_allowed, axis=0)
        if holding_allowed is not None:
            values = np.take(values, holding_allowed, axis=1)
        if inner is None:
            collapsed = values.sum(axis=(0, 1), dtype=np.float64)
            for code, val in enumerate(collapsed):
                if val:
                    result[(int(code), None)] = float(val)
            return
        axis_map = {bucket.dim_a: 0, bucket.dim_b: 1, bucket.dim_c: 2}
        outer_axis = axis_map[outer]
        inner_axis = axis_map[inner]
        axes = [ax for ax in range(3) if ax not in {outer_axis, inner_axis}]
        for idx in np.ndindex(values.shape):
            val = float(values[idx])
            if not val:
                continue
            o = idx[outer_axis]
            i = idx[inner_axis]
            result[(int(o), int(i))] = result.get((int(o), int(i)), 0.0) + val

    def _from_sparse_triple(key: tuple[str, str, str]) -> None:
        bucket = preagg.triples_sparse[key]
        n_b, n_c = bucket.shape[1], bucket.shape[2]
        for idx in range(len(bucket.flat_idx)):
            flat = int(bucket.flat_idx[idx])
            a = flat // (n_b * n_c)
            rem = flat % (n_b * n_c)
            b = rem // n_c
            c = rem % n_c
            if cargo_allowed is not None and a not in set(cargo_allowed):
                continue
            if holding_allowed is not None and b not in set(holding_allowed):
                continue
            code_map = {bucket.dim_a: a, bucket.dim_b: b, bucket.dim_c: c}
            if metric == "volume":
                val = float(bucket.volume[idx])
            elif metric == "base":
                val = float(bucket.base[idx, year_index])
            elif metric == "rules":
                val = float(bucket.rules[idx, year_index])
            elif metric == "charge":
                val = float(bucket.charge[idx, year_index])
            else:
                val = float(bucket.charge[idx, prev_year_index])
            if not val:
                continue
            o = code_map[outer]
            i = None if inner is None else code_map[inner]
            result[(int(o), int(i) if i is not None else None)] = (
                result.get((int(o), int(i) if i is not None else None), 0.0) + val
            )

    if cargo_allowed is None and holding_allowed is None:
        if inner is None:
            _from_single(outer)
        else:
            key = (outer, inner)
            if key in preagg.pairs_dense:
                _from_dense_pair(key, sum_outer=False)
            elif key in preagg.pairs_sparse:
                _from_sparse_pair(key)
        return result

    if cargo_allowed is not None and holding_allowed is None:
        if inner is None and outer == FILTER_OUTER:
            _from_single(FILTER_OUTER)
        else:
            key = (FILTER_OUTER, outer if inner is None else outer)
            if inner is not None:
                key = (FILTER_OUTER, outer) if outer != FILTER_OUTER else (outer, inner)
            if key not in preagg.pairs_dense and inner is not None:
                key = (outer, inner)
            if key in preagg.pairs_dense:
                _from_dense_pair(key, sum_outer=inner is not None)
            elif key in preagg.pairs_sparse:
                _from_sparse_pair(key)
        return result

    if holding_allowed is not None and cargo_allowed is None:
        if inner is None and outer == FILTER_INNER:
            _from_single(FILTER_INNER)
        else:
            key = (FILTER_INNER, outer) if outer != FILTER_INNER else (outer, inner or FILTER_INNER)
            if inner is not None and outer != FILTER_INNER:
                key = (FILTER_INNER, outer)
            if key in preagg.pairs_dense:
                _from_dense_pair(key, sum_outer=inner is not None)
            elif key in preagg.pairs_sparse:
                _from_sparse_pair(key)
        return result

    # Both filters active
    if inner is None and outer in {FILTER_OUTER, FILTER_INNER}:
        key = (FILTER_OUTER, FILTER_INNER)
        if key in preagg.pairs_dense:
            _from_dense_pair(key, sum_outer=False)
        elif key in preagg.pairs_sparse:
            _from_sparse_pair(key)
        return result

    triple_key = (FILTER_OUTER, FILTER_INNER, outer if inner is None else outer)
    if triple_key in preagg.triples_dense:
        _from_dense_triple(triple_key)
    elif triple_key in preagg.triples_sparse:
        _from_sparse_triple(triple_key)
    elif inner is not None:
        triple_key = (FILTER_OUTER, FILTER_INNER, outer)
        if triple_key in preagg.triples_dense:
            _from_dense_triple(triple_key)
        elif triple_key in preagg.triples_sparse:
            _from_sparse_triple(triple_key)
    return result


def _codes_to_labels(
    preagg: EffectsPreAggregate,
    *,
    outer: str,
    inner: str | None,
    sums: dict[tuple[int, int | None], float],
    include_subtotals: bool,
) -> dict[tuple[str, ...], Decimal]:
    buckets: dict[tuple[str, ...], Decimal] = defaultdict(Decimal)
    outer_totals: dict[int, Decimal] = defaultdict(Decimal)

    for (o_code, i_code), val in sums.items():
        if i_code is None:
            label = _label_for_code(preagg, outer, int(o_code))
            buckets[(label,)] += Decimal(str(val))
        else:
            outer_label = _label_for_code(preagg, outer, int(o_code))
            inner_label = _label_for_code(preagg, inner or outer, int(i_code))
            buckets[(outer_label, inner_label)] += Decimal(str(val))
            outer_totals[int(o_code)] += Decimal(str(val))

    if include_subtotals and inner is not None:
        for o_code, total in outer_totals.items():
            outer_label = _label_for_code(preagg, outer, int(o_code))
            buckets[(outer_label, "ИТОГО")] = total

    return dict(buckets)


def aggregate_preaggregate_buckets(
    preagg: EffectsPreAggregate,
    *,
    year: int,
    prev_year: int,
    group_by: str,
    group_by_inner: str,
    cargo_groups: list[str],
    holdings: list[str],
) -> dict[tuple[str, ...], tuple[Decimal, Decimal, Decimal]]:
    year_index = preagg.years.index(year)
    prev_year_index = preagg.years.index(prev_year)
    outer = group_by if group_by in GROUP_BY_CHOICES else FILTER_OUTER
    inner = None if group_by_inner == "none" else group_by_inner

    base_sums = _group_sums(
        preagg,
        group_by=group_by,
        group_by_inner=group_by_inner,
        cargo_groups=cargo_groups,
        holdings=holdings,
        metric="base",
        year_index=year_index,
        prev_year_index=prev_year_index,
    )
    rules_sums = _group_sums(
        preagg,
        group_by=group_by,
        group_by_inner=group_by_inner,
        cargo_groups=cargo_groups,
        holdings=holdings,
        metric="rules",
        year_index=year_index,
        prev_year_index=prev_year_index,
    )
    prev_sums = _group_sums(
        preagg,
        group_by=group_by,
        group_by_inner=group_by_inner,
        cargo_groups=cargo_groups,
        holdings=holdings,
        metric="prev_charge",
        year_index=year_index,
        prev_year_index=prev_year_index,
    )

    all_keys = set(base_sums) | set(rules_sums) | set(prev_sums)
    base_labels = _codes_to_labels(
        preagg,
        outer=outer,
        inner=inner,
        sums=base_sums,
        include_subtotals=inner is not None,
    )
    rules_labels = _codes_to_labels(
        preagg,
        outer=outer,
        inner=inner,
        sums=rules_sums,
        include_subtotals=inner is not None,
    )
    prev_labels = _codes_to_labels(
        preagg,
        outer=outer,
        inner=inner,
        sums=prev_sums,
        include_subtotals=inner is not None,
    )

    label_keys = set(base_labels) | set(rules_labels) | set(prev_labels)
    return {
        key: (
            base_labels.get(key, Decimal("0")),
            rules_labels.get(key, Decimal("0")),
            prev_labels.get(key, Decimal("0")),
        )
        for key in label_keys
    }


def aggregate_preaggregate_value(
    preagg: EffectsPreAggregate,
    *,
    group_by: str,
    group_by_inner: str,
    cargo_groups: list[str],
    holdings: list[str],
    metric: str,
    year_index: int | None = None,
    prev_year_index: int | None = None,
) -> dict[tuple[str, ...], Decimal]:
    outer = group_by if group_by in GROUP_BY_CHOICES else FILTER_OUTER
    inner = None if group_by_inner == "none" else group_by_inner
    sums = _group_sums(
        preagg,
        group_by=group_by,
        group_by_inner=group_by_inner,
        cargo_groups=cargo_groups,
        holdings=holdings,
        metric=metric,
        year_index=year_index or 0,
        prev_year_index=prev_year_index or 0,
    )
    return _codes_to_labels(
        preagg,
        outer=outer,
        inner=inner,
        sums=sums,
        include_subtotals=inner is not None,
    )


def aggregate_preaggregate_year_values(
    preagg: EffectsPreAggregate,
    *,
    group_by: str,
    group_by_inner: str,
    cargo_groups: list[str],
    holdings: list[str],
    metric: str = "charge",
) -> dict[tuple[str, ...], dict[int, Decimal]]:
    year_values: dict[tuple[str, ...], dict[int, Decimal]] = {}
    for year_index, year in enumerate(preagg.years):
        buckets = aggregate_preaggregate_value(
            preagg,
            group_by=group_by,
            group_by_inner=group_by_inner,
            cargo_groups=cargo_groups,
            holdings=holdings,
            metric=metric,
            year_index=year_index,
            prev_year_index=year_index,
        )
        for key, value in buckets.items():
            year_values.setdefault(key, {})[year] = value
    return year_values
