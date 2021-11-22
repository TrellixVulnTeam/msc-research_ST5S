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

from dataclasses import dataclass
from typing import final
from typing import Optional
from typing import Sequence

import torch
from torch.distributions import Normal

from s12045.frameworks.helper.reconstructions import make_reconstruction_loss
from s12045.frameworks.helper.reconstructions import ReconLossHandler
from s12045.frameworks.vae._supervised__tvae import TripletVae
from s12045.frameworks.vae._weaklysupervised__adavae import AdaVae
from s12045.nn.loss.softsort import torch_mse_rank_loss
from s12045.nn.loss.softsort import spearman_rank_loss


# ========================================================================= #
# tvae                                                                      #
# ========================================================================= #


class DataOverlapRankVae(TripletVae):
    """
    This converges really well!
    - but doesn't introduce axis alignment as well if there is no additional
      inward pressure term like triplet to move representations closer together
    """

    REQUIRED_OBS = 1

    @dataclass
    class cfg(TripletVae.cfg):
        # compatibility
        ada_thresh_mode: str = 'dist'  # kl, symmetric_kl, dist, sampled_dist
        ada_thresh_ratio: float = 0.5
        adat_triplet_share_scale: float = 0.95
        # OVERLAP VAE
        overlap_loss: Optional[str] = None
        overlap_num: int = 1024
        # AUGMENT
        overlap_augment_mode: str = 'none'
        overlap_augment: Optional[dict] = None
        # REPRESENTATIONS
        overlap_repr: str = 'deterministic'  # deterministic, stochastic
        overlap_rank_mode: str = 'spearman_rank'  # spearman_rank, mse_rank
        overlap_inward_pressure_masked: bool = False
        overlap_inward_pressure_scale: float = 0.1

    def __init__(self, model: 'AutoEncoder', cfg: cfg = None, batch_augment=None):
        # TODO: duplicate code
        super().__init__(model=model, cfg=cfg, batch_augment=batch_augment)
        # initialise
        if self.cfg.overlap_augment_mode != 'none':
            assert self.cfg.overlap_augment is not None, 'if cfg.overlap_augment_mode is not "none", then cfg.overlap_augment must be defined.'
        # set augment and instantiate if needed
        self._augment = None
        if isinstance(self._augment, dict):
            import hydra
            self._augment = hydra.utils.instantiate(self.cfg.overlap_augment)
            assert callable(self._augment), f'augment is not callable: {repr(self._augment)}'
        # get overlap loss
        overlap_loss = self.cfg.overlap_loss if (self.cfg.overlap_loss is not None) else self.cfg.recon_loss
        self.__overlap_handler: ReconLossHandler = make_reconstruction_loss(overlap_loss, reduction='mean')

    @final
    @property
    def overlap_handler(self) -> ReconLossHandler:
        return self.__overlap_handler

    def hook_compute_ave_aug_loss(self, ds_posterior: Sequence[Normal], ds_prior, zs_sampled, xs_partial_recon, xs_targ: Sequence[torch.Tensor]):
        # ++++++++++++++++++++++++++++++++++++++++++ #
        # 1. augment batch
        (x_targ_orig,) = xs_targ
        with torch.no_grad():
            (x_targ,) = self.augment_triplet_targets(xs_targ)
        (d_posterior,) = ds_posterior
        (z_sampled,) = zs_sampled
        # 2. generate random pairs -- this does not generate unique pairs
        a_idxs, p_idxs = torch.randint(len(x_targ), size=(2, self.cfg.overlap_num), device=x_targ.device)
        # ++++++++++++++++++++++++++++++++++++++++++ #
        # compute image distances
        with torch.no_grad():
            ap_recon_dists = self.overlap_handler.compute_pairwise_loss(x_targ[a_idxs], x_targ[p_idxs])
        # ++++++++++++++++++++++++++++++++++++++++++ #
        # get representations
        if self.cfg.overlap_repr == 'deterministic':
            a_z, p_z = d_posterior.loc[a_idxs], d_posterior.loc[p_idxs]
        elif self.cfg.overlap_repr == 'stochastic':
            a_z, p_z = z_sampled[a_idxs], z_sampled[p_idxs]
        else:
            raise KeyError(f'invalid overlap_repr mode: {repr(self.cfg.overlap_repr)}')
        # DISENTANGLE!
        # compute adaptive mask & weight deltas
        a_posterior = Normal(d_posterior.loc[a_idxs], d_posterior.scale[a_idxs])
        p_posterior = Normal(d_posterior.loc[p_idxs], d_posterior.scale[p_idxs])
        share_mask = AdaVae.compute_shared_mask_from_posteriors(a_posterior, p_posterior, thresh_mode=self.cfg.ada_thresh_mode, ratio=self.cfg.ada_thresh_ratio)
        deltas = torch.where(share_mask, self.cfg.adat_triplet_share_scale * (a_z - p_z), (a_z - p_z))
        # compute representation distances
        ap_repr_dists = torch.abs(deltas).sum(dim=-1)
        # ++++++++++++++++++++++++++++++++++++++++++ #
        if self.cfg.overlap_rank_mode == 'mse_rank':
            loss = torch_mse_rank_loss(ap_repr_dists, ap_recon_dists.detach(), dims=-1, reduction='mean')
            loss_logs = {'mse_rank_loss': loss}
        elif self.cfg.overlap_rank_mode == 'spearman_rank':
            loss = - spearman_rank_loss(ap_repr_dists, ap_recon_dists.detach(), nan_to_num=True)
            loss_logs = {'spearman_rank_loss': loss}
        else:
            raise KeyError(f'invalid overlap_rank_mode: {repr(self.cfg.overlap_repr)}')
        # ++++++++++++++++++++++++++++++++++++++++++ #
        # inward pressure
        if self.cfg.overlap_inward_pressure_masked:
            in_deltas = torch.abs(deltas) * share_mask
        else:
            in_deltas = torch.abs(deltas)
        # compute inward pressure
        inward_pressure = self.cfg.overlap_inward_pressure_scale * in_deltas.mean()
        loss += inward_pressure
        # ++++++++++++++++++++++++++++++++++++++++++ #
        # return the loss
        return loss, {
            **loss_logs,
            'inward_pressure': inward_pressure,
        }

    def augment_triplet_targets(self, xs_targ):
        # TODO: duplicate code
        if self.cfg.overlap_augment_mode == 'none':
            aug_xs_targ = xs_targ
        elif (self.cfg.overlap_augment_mode == 'augment') or (self.cfg.overlap_augment_mode == 'augment_each'):
            # recreate augment each time
            if self.cfg.overlap_augment_mode == 'augment_each':
                import hydra
                self._augment = hydra.utils.instantiate(self.cfg.overlap_augment)
            # augment on correct device
            aug_xs_targ = [self._augment(x_targ) for x_targ in xs_targ]
            # checks
            assert all(a.shape == b.shape for a, b in zip(xs_targ, aug_xs_targ))
        else:
            raise KeyError(f'invalid cfg.overlap_augment_mode={repr(self.cfg.overlap_augment_mode)}')
        return aug_xs_targ


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
