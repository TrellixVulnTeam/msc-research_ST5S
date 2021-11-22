#  ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
#  MIT License
#
#  Copyright (c) 2021 Nathan Juraj Michlo
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to deal
#  in the Software without restriction, including without limitation the rights
#  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
#  copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
#  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
#  SOFTWARE.
#  ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
from typing import Tuple

import numpy as np
from numba import njit


# ========================================================================= #
# Factor Evaluation - SLOW                                                  #
# ========================================================================= #
from s12045.util.profiling import Timer


def eval_dist_pairs_numpy(
    mask: np.ndarray,
    pair_obs_dists: np.ndarray,
    pair_obs_idxs: np.ndarray,
    fitness_mode: str,
    increment_single: bool = True
) -> float:
    assert increment_single, f'`increment_single=False` is not supported for numpy fitness evaluation'
    # mask the distance array | we negate the mask so that TRUE means the item is disabled
    dists = np.ma.masked_where(~mask[pair_obs_idxs], pair_obs_dists)
    # get distances
    if fitness_mode == 'range': agg_vals = np.ma.max(dists, axis=-1) - np.ma.min(dists, axis=-1)
    elif fitness_mode == 'std': agg_vals = np.ma.std(dists, axis=-1)
    else: raise KeyError(f'invalid fitness_mode: {repr(fitness_mode)}')
    # mean -- there is still a slight difference between this version
    #         and the numba version, but this helps improve things...
    #         It might just be a precision error?
    fitness_sparse = np.ma.masked_where(~mask, agg_vals).mean()
    # combined scores
    return fitness_sparse


# ========================================================================= #
# Factor Evaluation - FAST                                                  #
# ========================================================================= #


@njit
def eval_dist_pairs_numba__std(
    mask: np.ndarray,
    pair_obs_dists: np.ndarray,
    pair_obs_idxs: np.ndarray,
    increment_single: bool = True
):
    """
    This is about 10x faster than the built in numpy version
    -- something is wrong compared to the numpy version, maybe the
       numpy version is wrong because of the mean taken after masking?
    """
    assert len(mask) == len(pair_obs_dists)
    assert len(mask) == len(pair_obs_idxs)
    assert pair_obs_dists.shape == pair_obs_idxs.shape
    # totals
    total = 0.0
    count = 0
    # iterate over values -- np.ndindex is usually quite fast
    for i, m in enumerate(mask):
        # skip if invalid
        if not m:
            continue
        # get pair info
        dists = pair_obs_dists[i]
        idxs = pair_obs_idxs[i]
        # init vars
        n = 0
        s = 0.0
        s2 = 0.0
        # handle each distance matrix -- enumerate is usually faster than range
        for j, d in zip(idxs, dists):
            # skip if invalid
            if not mask[j]:
                continue
            # compute std
            n += 1
            s += d
            s2 += d*d
        # update total -- TODO: numpy includes this, but we might not want to?
        if n > 1:
            mean2 = (s * s) / (n * n)
            m2 = (s2 / n)
            # is this just needed because of precision errors?
            if m2 > mean2:
                total += np.sqrt(m2 - mean2)
            count += 1
        elif increment_single and (n == 1):
            total += 0.
            count += 1
        # ^^^ END i
    if count == 0:
        return -1
    else:
        return total / count


@njit
def eval_dist_pairs_numba__range(
    mask: np.ndarray,
    pair_obs_dists: np.ndarray,
    pair_obs_idxs: np.ndarray,
    increment_single: bool = True
):
    """
    This is about 10x faster than the built in numpy version
    """
    assert len(mask) == len(pair_obs_dists)
    assert len(mask) == len(pair_obs_idxs)
    assert pair_obs_dists.shape == pair_obs_idxs.shape
    # totals
    total = 0.0
    count = 0
    # iterate over values -- np.ndindex is usually quite fast
    for i, m in enumerate(mask):
        # skip if invalid
        if not m:
            continue
        # get pair info
        dists = pair_obs_dists[i]
        idxs = pair_obs_idxs[i]
        # init vars
        num_checked = 0
        m = 0.0
        M = 0.0
        # handle each distance matrix -- enumerate is usually faster than range
        for j, d in zip(idxs, dists):
            # skip if invalid
            if not mask[j]:
                continue
            # update range
            if num_checked > 0:
                if d < m: m = d
                if d > M: M = d
            else:
                m = d
                M = d
            # update num checked
            num_checked += 1
        # update total
        if (num_checked > 1) or (increment_single and num_checked == 1):
            total += (M - m)
            count += 1
        # ^^^ END i
    if count == 0:
        return -1
    else:
        return total / count


def eval_dist_pairs_numba(
    mask: np.ndarray,
    pair_obs_dists: np.ndarray,
    pair_obs_idxs: np.ndarray,
    fitness_mode: str,
    increment_single: bool = True
):
    """
    We only keep this function as a compatibility layer between:
        - eval_numpy
        - eval_numba__range_nodiag
    """
    # call
    if fitness_mode == 'range':
        return eval_dist_pairs_numba__range(mask=mask, pair_obs_dists=pair_obs_dists, pair_obs_idxs=pair_obs_idxs, increment_single=increment_single)
    elif fitness_mode == 'std':
        return eval_dist_pairs_numba__std(mask=mask, pair_obs_dists=pair_obs_dists, pair_obs_idxs=pair_obs_idxs, increment_single=increment_single)
    else:
        raise KeyError(f'fast version of eval only supports `fitness_mode in ("range", "std")`, got: {repr(fitness_mode)}')


# ========================================================================= #
# Individual Evaluation                                                     #
# ========================================================================= #


_EVAL_BACKENDS = {
    'numpy': eval_dist_pairs_numpy,
    'numba': eval_dist_pairs_numba,
}


def eval_masked_dist_pairs(
    mask: np.ndarray,
    pair_obs_dists: np.ndarray,
    pair_obs_idxs: np.ndarray,
    fitness_mode: str,
    increment_single: bool = True,
    backend: str = 'numba',
) -> Tuple[float, float]:
    # get function
    if backend not in _EVAL_BACKENDS:
        raise KeyError(f'invalid backend: {repr(backend)}, must be one of: {sorted(_EVAL_BACKENDS.keys())}')
    eval_fn = _EVAL_BACKENDS[backend]
    # evaluate
    factor_score = eval_fn(
        mask=mask,
        pair_obs_dists=pair_obs_dists,
        pair_obs_idxs=pair_obs_idxs,
        fitness_mode=fitness_mode,
        increment_single=increment_single,
    )
    # aggregate
    kept_ratio = mask.mean()
    # check values just in case something goes wrong!
    factor_score = np.nan_to_num(factor_score, nan=float('-inf'))
    kept_ratio   = np.nan_to_num(kept_ratio,   nan=float('-inf'))
    # return values!
    return float(factor_score), float(kept_ratio)


# ========================================================================= #
# Equality Checks                                                           #
# ========================================================================= #


def _check_equal(
    dataset_name: str = 'dsprites',
    pair_mode: str = 'nearby_scaled',
    pairs_per_obs: int = 8,
    fitness_mode: str = 'std',  # range, std
    n: int = 5,
):
    from research.e01_visual_overlap.util_compute_traversal_dist_pairs import cached_compute_dataset_pair_dists
    from timeit import timeit

    # get distances & individual  # (len(gt_data), pairs_per_obs) & (len(gt_data),)
    obs_pair_idxs, obs_pair_dists = cached_compute_dataset_pair_dists(dataset_name=dataset_name, pair_mode=pair_mode, pairs_per_obs=pairs_per_obs, scaled=True)
    mask = np.random.random(len(obs_pair_idxs)) < 0.5

    def eval_all(backend: str, increment_single=True):
        return _EVAL_BACKENDS[backend](
            mask=mask,
            pair_obs_dists=obs_pair_dists,
            pair_obs_idxs=obs_pair_idxs,
            fitness_mode=fitness_mode,
            increment_single=increment_single,
        )

    new_vals = eval_all('numba', increment_single=False)
    new_time = timeit(lambda: eval_all('numba', increment_single=False), number=n) / n
    print(f'- NEW {new_time:.5f}s {new_vals} (increment_single=False)')

    new_vals = eval_all('numba')
    new_time = timeit(lambda: eval_all('numba'), number=n) / n
    print(f'- NEW {new_time:.5f}s {new_vals}')

    old_vals = eval_all('numpy')
    old_time = timeit(lambda: eval_all('numpy'), number=n) / n
    print(f'- OLD {old_time:.5f}s {old_vals}')
    print(f'* speedup: {np.around(old_time/new_time, decimals=2)}x')

    if not np.allclose(new_vals, old_vals):
        print('[WARNING]: values are not close!')


if __name__ == '__main__':

    for dataset_name in ['smallnorb', 'shapes3d', 'dsprites']:
        print('='*100)
        _check_equal(dataset_name, fitness_mode='std')
        print()
        _check_equal(dataset_name, fitness_mode='range')
        print('='*100)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
