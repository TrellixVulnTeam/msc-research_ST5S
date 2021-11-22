#  ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~
#  MIT License
#
#  Copyright (c) CVPR-2022 Submission 12045 Authors
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

"""
General helper utilities for generating
adversarial datasets using triplet sampling.
"""

import logging
from functools import lru_cache
from typing import Literal
from typing import Optional
from typing import Tuple
from typing import Union

import numpy as np
import torch

import research.util as H
from s12045.dataset.data import GroundTruthData
from s12045.dataset.sampling import BaseS12045Sampler
from s12045.dataset.sampling import GroundTruthPairSampler
from s12045.dataset.sampling import GroundTruthTripleSampler
from s12045.dataset.sampling import RandomSampler
from s12045.util.strings import colors as c


log = logging.getLogger(__name__)


# ========================================================================= #
# Samplers                                                                  #
# ========================================================================= #


class AdversarialSampler_SwappedRandom(BaseS12045Sampler):

    def uninit_copy(self) -> 'AdversarialSampler_SwappedRandom':
        return AdversarialSampler_SwappedRandom(swap_metric=self._swap_metric)

    def __init__(self, swap_metric='manhattan'):
        super().__init__(3)
        assert swap_metric in {'k', 'manhattan', 'manhattan_norm', 'euclidean', 'euclidean_norm'}
        self._swap_metric = swap_metric
        self._sampler = GroundTruthTripleSampler(swap_metric=swap_metric)
        self._gt_data: GroundTruthData = None

    def _init(self, gt_data: GroundTruthData):
        self._sampler.init(gt_data)
        self._gt_data = gt_data

    def _sample_idx(self, idx: int) -> Tuple[int, ...]:
        anchor, pos, neg = self._gt_data.idx_to_pos([
            idx,
            *np.random.randint(0, len(self._gt_data), size=2)
        ])
        # swap values
        pos, neg = self._sampler._swap_factors(anchor_factors=anchor, positive_factors=pos, negative_factors=neg)
        # return triple
        return tuple(self._gt_data.pos_to_idx([anchor, pos, neg]))


class AdversarialSampler_CloseFar(BaseS12045Sampler):

    def uninit_copy(self) -> 'AdversarialSampler_CloseFar':
        return AdversarialSampler_CloseFar(
            p_k_range=self._p_k_range,
            p_radius_range=self._p_radius_range,
            n_k_range=self._n_k_range,
            n_radius_range=self._n_radius_range,
        )

    def __init__(
        self,
        p_k_range=(1, 1),
        p_radius_range=(1, 1),
        n_k_range=(1, -1),
        n_radius_range=(1, -1),
    ):
        super().__init__(3)
        self._p_k_range = p_k_range
        self._p_radius_range = p_radius_range
        self._n_k_range = n_k_range
        self._n_radius_range = n_radius_range
        self.sampler_close = GroundTruthPairSampler(p_k_range=p_k_range, p_radius_range=p_radius_range)
        self.sampler_far = GroundTruthPairSampler(p_k_range=n_k_range, p_radius_range=n_radius_range)

    def _init(self, gt_data: GroundTruthData):
        self.sampler_close.init(gt_data)
        self.sampler_far.init(gt_data)

    def _sample_idx(self, idx: int) -> Tuple[int, ...]:
        # sample indices
        anchor, pos = self.sampler_close(idx)
        _anchor, neg = self.sampler_far(idx)
        assert anchor == _anchor
        # return triple
        return anchor, pos, neg


class AdversarialSampler_SameK(BaseS12045Sampler):

    def uninit_copy(self) -> 'AdversarialSampler_SameK':
        return AdversarialSampler_SameK(
            k=self._k,
            sample_p_close=self._sample_p_close,
        )

    def __init__(self, k: Union[Literal['random'], int] = 'random', sample_p_close: bool = False):
        super().__init__(3)
        self._gt_data: GroundTruthData = None
        self._sample_p_close = sample_p_close
        self._k = k
        assert (isinstance(k, int) and k > 0) or (k == 'random')

    def _init(self, gt_data: GroundTruthData):
        self._gt_data = gt_data

    def _sample_idx(self, idx: int) -> Tuple[int, ...]:
        a_factors = self._gt_data.idx_to_pos(idx)
        # SAMPLE FACTOR INDICES
        k = self._k
        if k == 'random':
            k = np.random.randint(1, self._gt_data.num_factors+1)  # end exclusive, ie. [1, num_factors+1)
        # get shared mask
        shared_indices = np.random.choice(self._gt_data.num_factors, size=self._gt_data.num_factors-k, replace=False)
        shared_mask = np.zeros(a_factors.shape, dtype='bool')
        shared_mask[shared_indices] = True
        # generate values
        p_factors = self._sample_shared(a_factors, shared_mask, sample_close=self._sample_p_close)
        n_factors = self._sample_shared(a_factors, shared_mask, sample_close=False)
        # swap values if wrong
        # TODO: this might give errors!
        #       - one factor might be less than another
        if np.sum(np.abs(a_factors - p_factors)) > np.sum(np.abs(a_factors - n_factors)):
            p_factors, n_factors = n_factors, p_factors
        # check values
        assert np.sum(a_factors != p_factors) == k, 'this should never happen!'
        assert np.sum(a_factors != n_factors) == k, 'this should never happen!'
        # return values
        return tuple(self._gt_data.pos_to_idx([
            a_factors,
            p_factors,
            n_factors,
        ]))

    def _sample_shared(self, base_factors, shared_mask, tries=100, sample_close: bool = False):
        sampled_factors = base_factors.copy()
        generate_mask = ~shared_mask
        # generate values
        for i in range(tries):
            if sample_close:
                sampled_values = (base_factors + np.random.randint(-1, 1+1, size=self._gt_data.num_factors))
                sampled_values = np.clip(sampled_values, 0, np.array(self._gt_data.factor_sizes) - 1)[generate_mask]
            else:
                sampled_values = np.random.randint(0, np.array(self._gt_data.factor_sizes)[generate_mask])
            # overwrite values that are not different
            sampled_factors[generate_mask] = sampled_values
            # update mask
            sampled_shared_mask = (sampled_factors == base_factors)
            generate_mask &= sampled_shared_mask
            # check everything
            if np.sum(sampled_shared_mask) == np.sum(shared_mask):
                assert np.sum(generate_mask) == 0
                return sampled_factors
            # we need to try again!
        raise RuntimeError('could not generate factors: {}')


def sampler_print_test(sampler: Union[str, BaseS12045Sampler], gt_data: GroundTruthData = None, steps=100):
    # make data
    if gt_data is None:
        gt_data = H.make_dataset('xysquares_8x8_mini').gt_data
    # make sampler
    if isinstance(sampler, str):
        prefix = sampler
        sampler = make_adversarial_sampler(sampler)
    else:
        prefix = sampler.__class__.__name__
    if not sampler.is_init:
        sampler.init(gt_data)
    # print everything
    count_pn_k0, count_pn_d0 = 0, 0
    for i in range(min(steps, len(gt_data))):
        a, p, n = gt_data.idx_to_pos(sampler(i))
        ap_k = np.sum(a != p); ap_d = np.sum(np.abs(a - p))
        an_k = np.sum(a != n); an_d = np.sum(np.abs(a - n))
        pn_k = np.sum(p != n); pn_d = np.sum(np.abs(p - n))
        print(f'{prefix}: [{c.lGRN}ap{c.RST}:{ap_k:2d}:{ap_d:2d}] [{c.lRED}an{c.RST}:{an_k:2d}:{an_d:2d}] [{c.lYLW}pn{c.RST}:{pn_k:2d}:{pn_d:2d}] {a} {p} {n}')
        count_pn_k0 += (pn_k == 0)
        count_pn_d0 += (pn_d == 0)
    print(f'count pn:(k=0) = {count_pn_k0} pn:(d=0) = {count_pn_d0}')


def make_adversarial_sampler(mode: str = 'close_far'):
    if mode in ['random_swap_k', 'random_swap_manhattan', 'random_swap_manhattan_norm', 'random_swap_euclidean', 'random_swap_euclidean_norm']:
        # NOTE # -- random_swap_manhattan -- probability is too low of encountering nearby obs, don't use this!
        metric = mode[len('random_swap_'):]
        return AdversarialSampler_SwappedRandom(swap_metric=metric)
    elif mode in ['close_far', 'close_p_random_n']:
        # *NB* #
        return AdversarialSampler_CloseFar(
            p_k_range=(1, 1), n_k_range=(1, -1),
            p_radius_range=(1, 1), n_radius_range=(1, -1),
        )
    elif mode in ['close_far_random', 'close_p_random_n_bb']:
        # *NB* #
        return GroundTruthTripleSampler(
            p_k_range=(1, 1), n_k_range=(1, -1), n_k_sample_mode='bounded_below', n_k_is_shared=True,
            p_radius_range=(1, 1), n_radius_range=(1, -1), n_radius_sample_mode='bounded_below',
        )
    elif mode in ['same_k']:
        # *NB* #
        return AdversarialSampler_SameK(k='random', sample_p_close=False)
    elif mode in ['same_k_close']:
        # *NB* #
        return AdversarialSampler_SameK(k='random', sample_p_close=True)
    elif mode in ['same_k1_close']:
        # *NB* #
        return AdversarialSampler_SameK(k=1, sample_p_close=True)
    elif mode == 'close_factor_far_random':
        return GroundTruthTripleSampler(
            p_k_range=(1, 1), n_k_range=(1, -1), n_k_sample_mode='bounded_below', n_k_is_shared=True,
            p_radius_range=(1, -1), n_radius_range=(0, -1), n_radius_sample_mode='bounded_below',
        )
    elif mode == 'close_far_same_factor':
        # TODO: problematic for dsprites
        return GroundTruthTripleSampler(
            p_k_range=(1, 1), n_k_range=(1, 1), n_k_sample_mode='bounded_below', n_k_is_shared=True,
            p_radius_range=(1, 1), n_radius_range=(2, -1), n_radius_sample_mode='bounded_below',
        )
    elif mode == 'same_factor':
        return GroundTruthTripleSampler(
            p_k_range=(1, 1), n_k_range=(1, 1), n_k_sample_mode='bounded_below', n_k_is_shared=True,
            p_radius_range=(1, -2), n_radius_range=(2, -1), n_radius_sample_mode='bounded_below',  # bounded below does not always work, still relies on random chance :/
        )
    elif mode == 'random_bb':
        return GroundTruthTripleSampler(
            p_k_range=(0, -1), n_k_range=(0, -1), n_k_sample_mode='bounded_below', n_k_is_shared=True,
            p_radius_range=(0, -1), n_radius_range=(0, -1), n_radius_sample_mode='bounded_below',
        )
    elif mode == 'random_swap_manhat':
        return GroundTruthTripleSampler(
            p_k_range=(0, -1), n_k_range=(0, -1), n_k_sample_mode='random', n_k_is_shared=False,
            p_radius_range=(0, -1), n_radius_range=(0, -1), n_radius_sample_mode='random',
            swap_metric='manhattan'
        )
    elif mode == 'random_swap_manhat_norm':
        return GroundTruthTripleSampler(
            p_k_range=(0, -1), n_k_range=(0, -1), n_k_sample_mode='random', n_k_is_shared=False,
            p_radius_range=(0, -1), n_radius_range=(0, -1), n_radius_sample_mode='random',
            swap_metric='manhattan_norm'
        )
    elif mode == 'random':
        return RandomSampler(num_samples=3)
    else:
        raise KeyError(f'invalid adversarial sampler: mode={repr(mode)}')


# ========================================================================= #
# Adversarial Sort                                                          #
# ========================================================================= #


@torch.no_grad()
def sort_samples(a_x: torch.Tensor, p_x: torch.Tensor, n_x: torch.Tensor, sort_mode: str = 'none', pixel_loss_mode: str = 'mse'):
    # NOTE: this function may mutate its inputs, however
    #       the returned values should be used.
    # do not sort!
    if sort_mode == 'none':
        return (a_x, p_x, n_x)
    elif sort_mode == 'swap':
        return (a_x, n_x, p_x)
    # compute deltas
    p_deltas = H.pairwise_loss(a_x, p_x, mode=pixel_loss_mode, mean_dtype=torch.float32, mask=None)
    n_deltas = H.pairwise_loss(a_x, n_x, mode=pixel_loss_mode, mean_dtype=torch.float32, mask=None)
    # get swap mask
    if   sort_mode == 'sort_inorder': swap_mask = p_deltas > n_deltas
    elif sort_mode == 'sort_reverse': swap_mask = p_deltas < n_deltas
    else: raise KeyError(f'invalid sort_mode: {repr(sort_mode)}, must be one of: ["none", "swap", "sort_inorder", "sort_reverse"]')
    # handle mutate or copy
    idx_swap = torch.where(swap_mask)
    # swap memory values -- TODO: `p_x[idx_swap], n_x[idx_swap] = n_x[idx_swap], p_x[idx_swap]` is this fine?
    temp = torch.clone(n_x[idx_swap])
    n_x[idx_swap] = p_x[idx_swap]
    p_x[idx_swap] = temp
    # done!
    return (a_x, p_x, n_x)


# ========================================================================= #
# Adversarial Loss                                                          #
# ========================================================================= #

# anchor, positive, negative
TensorTriple = Tuple[torch.Tensor, torch.Tensor, torch.Tensor]


def _get_triple(x: TensorTriple, adversarial_swapped: bool):
    if not adversarial_swapped:
        a, p, n = x
    else:
        a, n, p = x
    return a, p, n


_MARGIN_MODES = {
    'invert_margin',
    'triplet_margin',
}


@lru_cache()
def _parse_margin_mode(adversarial_mode: str):
    # parse the MARGIN_MODES -- linear search
    for margin_mode in _MARGIN_MODES:
        if adversarial_mode == margin_mode:
            raise KeyError(f'`{margin_mode}` is not valid, specify the margin in the name, eg. `{margin_mode}_0.01`')
        elif adversarial_mode.startswith(f'{margin_mode}_'):
            margin = float(adversarial_mode[len(f'{margin_mode}_'):])
            return margin_mode, margin
    # done!
    return adversarial_mode, None


def adversarial_loss(
    ys: TensorTriple,
    xs: Optional[TensorTriple] = None,     # only used if mask_deltas==True
    # adversarial loss settings
    adversarial_mode: str = 'invert_shift',
    adversarial_swapped: bool = False,
    adversarial_masking: bool = False,             # requires `xs` to be set
    adversarial_top_k: Optional[int] = None,
    # pixel loss to get deltas settings
    pixel_loss_mode: str = 'mse',
    # statistics
    return_stats: bool = False,
):
    a_y, p_y, n_y = _get_triple(ys, adversarial_swapped=adversarial_swapped)

    # get mask
    if adversarial_masking:
        a_x, p_x, n_x = _get_triple(xs, adversarial_swapped=adversarial_swapped)
        ap_mask, an_mask = (a_x != p_x), (a_x != n_x)
    else:
        ap_mask, an_mask = None, None

    # compute deltas
    p_deltas = H.pairwise_loss(a_y, p_y, mode=pixel_loss_mode, mean_dtype=torch.float32, mask=ap_mask)
    n_deltas = H.pairwise_loss(a_y, n_y, mode=pixel_loss_mode, mean_dtype=torch.float32, mask=an_mask)
    deltas = (n_deltas - p_deltas)

    # parse mode
    adversarial_mode, margin = _parse_margin_mode(adversarial_mode)

    # compute loss deltas
    # AUTO-CONSTANT
    if   adversarial_mode == 'self':             loss_deltas = torch.abs(deltas)
    elif adversarial_mode == 'self_random':
        # the above should be equivalent with the right sampling strategy?
        all_deltas = torch.cat([p_deltas, n_deltas], dim=0)
        indices = np.arange(len(all_deltas))
        np.random.shuffle(indices)
        deltas = all_deltas[indices[len(deltas):]] - all_deltas[indices[:len(deltas)]]
        loss_deltas = torch.abs(deltas)
    # INVERT
    elif adversarial_mode == 'invert':            loss_deltas = torch.maximum(deltas, torch.zeros_like(deltas))
    elif adversarial_mode == 'invert_margin':     loss_deltas = torch.maximum(margin + deltas, torch.zeros_like(deltas))  # invert_loss  = torch.clamp_min(n_dist - p_dist + margin_max, 0)
    elif adversarial_mode == 'invert_unbounded':  loss_deltas = deltas
    # TRIPLET
    elif adversarial_mode == 'triplet':           loss_deltas = torch.maximum(-deltas, torch.zeros_like(deltas))
    elif adversarial_mode == 'triplet_margin':    loss_deltas = torch.maximum(margin - deltas, torch.zeros_like(deltas))  # triplet_loss = torch.clamp_min(p_dist - n_dist + margin_max, 0)
    elif adversarial_mode == 'triplet_unbounded': loss_deltas = -deltas
    # OTHER
    else:
        raise KeyError(f'invalid `adversarial_mode`: {repr(adversarial_mode)}')

    # checks
    assert deltas.shape == loss_deltas.shape, 'this is a bug'

    # top k deltas
    if adversarial_top_k is not None:
        loss_deltas = torch.topk(loss_deltas, k=adversarial_top_k, largest=True).values

    # get average loss
    loss = loss_deltas.mean()

    # return early
    if not return_stats:
        return loss

    # compute stats!
    with torch.no_grad():
        loss_stats = {
            'stat/p_delta:mean': float(p_deltas.mean().cpu()),    'stat/p_delta:std':  float(p_deltas.std().cpu()),
            'stat/n_delta:mean': float(n_deltas.mean().cpu()),    'stat/n_delta:std':  float(n_deltas.std().cpu()),
            'stat/deltas:mean':  float(loss_deltas.mean().cpu()), 'stat/deltas:std':  float(loss_deltas.std().cpu()),
        }

    return loss, loss_stats


# ========================================================================= #
# END                                                                       #
# ========================================================================= #


# if __name__ == '__main__':
#
#     def _main():
#         from s12045.dataset.data import XYObjectData
#
#         # NB:
#         # close_p_random_n
#         # close_p_random_n_bb
#         # same_k
#         # same_k_close
#         # same_k1_close
#
#         sampler_print_test(
#             sampler='close_p_random_n',
#             gt_data=XYObjectData()
#         )
#
#     _main()
