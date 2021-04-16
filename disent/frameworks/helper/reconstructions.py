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

import warnings
from typing import final
from typing import Sequence

import torch
import torch.nn.functional as F

from disent.frameworks.helper.reductions import loss_reduction
from disent.frameworks.helper.util import compute_ave_loss


from disent.util.math_loss import torch_mse_rank_loss


# ========================================================================= #
# Reconstruction Loss Base                                                  #
# ========================================================================= #


class ReconLossHandler(object):

    def __init__(self, reduction: str = 'mean'):
        self._reduction = reduction

    def activate(self, x_partial: torch.Tensor):
        """
        The final activation of the model.
        - Never use this in a training loop.
        """
        raise NotImplementedError

    def activate_all(self, xs_partial: Sequence[torch.Tensor]):
        return [self.activate(x_partial) for x_partial in xs_partial]

    @final
    def compute_loss(self, x_recon: torch.Tensor, x_targ: torch.Tensor) -> torch.Tensor:
        """
        Takes in activated tensors
        :return: The computed reduced loss
        """
        assert x_recon.shape == x_targ.shape, f'x_recon.shape={x_recon.shape} x_targ.shape={x_targ.shape}'
        batch_loss = self.compute_unreduced_loss(x_recon, x_targ)
        loss = loss_reduction(batch_loss, reduction=self._reduction)
        return loss

    @final
    def compute_loss_from_partial(self, x_partial_recon: torch.Tensor, x_targ: torch.Tensor) -> torch.Tensor:
        """
        Takes in an **unactivated** tensor from the model
        as well as an original target from the dataset.
        :return: The computed reduced loss
        """
        assert x_partial_recon.shape == x_targ.shape, f'x_partial_recon.shape={x_partial_recon.shape} x_targ.shape={x_targ.shape}'
        batch_loss = self.compute_unreduced_loss_from_partial(x_partial_recon, x_targ)
        loss = loss_reduction(batch_loss, reduction=self._reduction)
        return loss


    @final
    def compute_ave_loss(self, xs_recon: Sequence[torch.Tensor], xs_targ: Sequence[torch.Tensor]) -> torch.Tensor:
        """
        Compute the average over losses computed from corresponding tensor pairs in the sequence.
        """
        return compute_ave_loss(self.compute_loss, xs_recon, xs_targ)

    @final
    def compute_ave_loss_from_partial(self, xs_partial_recon: Sequence[torch.Tensor], xs_targ: Sequence[torch.Tensor]) -> torch.Tensor:
        """
        Compute the average over losses computed from corresponding tensor pairs in the sequence.
        """
        return compute_ave_loss(self.compute_loss_from_partial, xs_partial_recon, xs_targ)

    def compute_unreduced_loss(self, x_recon: torch.Tensor, x_targ: torch.Tensor) -> torch.Tensor:
        """
        Takes in activated tensors
        Compute the loss without applying a reduction, the loss
        tensor should be the same shapes as the input tensors
        :return: The computed unreduced loss
        """
        raise NotImplementedError

    def compute_unreduced_loss_from_partial(self, x_partial_recon: torch.Tensor, x_targ: torch.Tensor) -> torch.Tensor:
        """
        Takes in an **unactivated** tensor from the model
        Compute the loss without applying a reduction, the loss
        tensor should be the same shapes as the input tensors
        :return: The computed unreduced loss
        """
        raise NotImplementedError


# ========================================================================= #
# Reconstruction Losses                                                     #
# ========================================================================= #


class ReconLossHandlerMse(ReconLossHandler):
    """
    MSE loss should be used with continuous targets between [0, 1].
    - using BCE for such targets is a prevalent error in VAE research.
    """

    def activate(self, x_partial: torch.Tensor) -> torch.Tensor:
        # we allow the model output x to generally be in the range [-1, 1] and scale
        # it to the range [0, 1] here to match the targets.
        # - this lets it learn more easily as the output is naturally centered on 1
        # - doing this here directly on the output is easier for visualisation etc.
        # - TODO: the better alternative is that we rather calculate the MEAN and STD over the dataset
        #         and normalise that.
        # - sigmoid is numerically not suitable with MSE
        return (x_partial + 1) / 2

    def compute_unreduced_loss(self, x_recon: torch.Tensor, x_targ: torch.Tensor) -> torch.Tensor:
        return F.mse_loss(x_recon, x_targ, reduction='none')

    def compute_unreduced_loss_from_partial(self, x_partial_recon: torch.Tensor, x_targ: torch.Tensor) -> torch.Tensor:
        return self.compute_unreduced_loss(self.activate(x_partial_recon), x_targ)


class ReconLossHandlerMae(ReconLossHandlerMse):
    """
    MAE loss should be used with continuous targets between [0, 1].
    """
    def compute_unreduced_loss(self, x_partial_recon, x_targ):
        return torch.abs(x_partial_recon - x_targ)


class ReconLossHandlerBce(ReconLossHandler):
    """
    BCE loss should only be used with binary targets {0, 1}.
    - ignoring this and not using MSE is a prevalent error in VAE research.
    """

    def activate(self, x_partial: torch.Tensor):
        # we allow the model output x to generally be in the range [-1, 1] and scale
        # it to the range [0, 1] here to match the targets.
        return torch.sigmoid(x_partial)

    def compute_unreduced_loss(self, x_recon: torch.Tensor, x_targ: torch.Tensor) -> torch.Tensor:
        warnings.warn('binary cross entropy not computed over logits is inaccurate!')
        return F.binary_cross_entropy(x_recon, x_targ, reduction='none')

    def compute_unreduced_loss_from_partial(self, x_partial_recon, x_targ):
        """
        Computes the Bernoulli loss for the sigmoid activation function
        REFERENCE:
            https://github.com/google-research/disentanglement_lib/blob/76f41e39cdeff8517f7fba9d57b09f35703efca9/disentanglement_lib/methods/shared/losses.py
            - the same when reduction=='mean_sum' for super().training_compute_loss()
        REFERENCE ALT:
            https://github.com/YannDubs/disentangling-vae/blob/master/disvae/models/losses.py
        """
        return F.binary_cross_entropy_with_logits(x_partial_recon, x_targ, reduction='none')


# ========================================================================= #
# Reconstruction Distributions                                              #
# ========================================================================= #


class ReconLossHandlerBernoulli(ReconLossHandlerBce):

    def compute_unreduced_loss(self, x_recon, x_targ):
        # This is exactly the same as the BCE version, but more 'correct'.
        warnings.warn('bernoulli not computed over logits might be inaccurate!')
        return -torch.distributions.Bernoulli(probs=x_recon).log_prob(x_targ)

    def compute_unreduced_loss_from_partial(self, x_partial_recon, x_targ):
        # This is exactly the same as the BCE version, but more 'correct'.
        return -torch.distributions.Bernoulli(logits=x_partial_recon).log_prob(x_targ)


class ReconLossHandlerContinuousBernoulli(ReconLossHandlerBce):
    """
    The continuous Bernoulli: fixing a pervasive error in variational autoencoders
    - Loaiza-Ganem G and Cunningham JP, NeurIPS 2019.
    - https://arxiv.org/abs/1907.06845
    """

    def compute_unreduced_loss(self, x_recon, x_targ):
        warnings.warn('Using continuous bernoulli distribution for reconstruction loss. This is not yet recommended!')
        warnings.warn('continuous bernoulli not computed over logits might be inaccurate!')
        # I think there is something wrong with this...
        return -torch.distributions.ContinuousBernoulli(probs=x_recon, lims=(0.49, 0.51)).log_prob(x_targ)

    def compute_unreduced_loss_from_partial(self, x_partial_recon, x_targ):
        warnings.warn('Using continuous bernoulli distribution for reconstruction loss. This is not yet recommended!')
        # I think there is something wrong with this...
        return -torch.distributions.ContinuousBernoulli(logits=x_partial_recon, lims=(0.49, 0.51)).log_prob(x_targ)


class ReconLossHandlerNormal(ReconLossHandlerMse):

    def compute_unreduced_loss(self, x_recon, x_targ):
        # this is almost the same as MSE, but scaled with a tiny offset
        # A value for scale should actually be passed...
        warnings.warn('Using normal distribution for reconstruction loss. This is not yet recommended!')
        return -torch.distributions.Normal(x_recon, 1.0).log_prob(x_targ)


# ========================================================================= #
# Factory                                                                   #
# ========================================================================= #



_RECON_LOSSES = {
    # ================================= #
    # from the normal distribution
    # binary values only in the set {0, 1}
    'mse': ReconLossHandlerMse,
    # mean absolute error
    'mae': ReconLossHandlerMae,
    # from the bernoulli distribution
    'bce': ReconLossHandlerBce,
    # reduces to bce
    # binary values only in the set {0, 1}
    'bernoulli': ReconLossHandlerBernoulli,
    # bernoulli with a computed offset to handle values in the range [0, 1]
    'continuous_bernoulli': ReconLossHandlerContinuousBernoulli,
    # handle all real values
    'normal': ReconLossHandlerNormal,
    # ================================= #
    # EXPERIMENTAL -- im just curious what would happen, haven't actually
    #                 done the maths or thought about this much.
}


def make_reconstruction_loss(name: str, reduction: str) -> ReconLossHandler:
    try:
        cls = _RECON_LOSSES[name]
    except KeyError:
        raise KeyError(f'Invalid vae reconstruction loss: {name}')
    # instantiate!
    return cls(reduction=reduction)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #

