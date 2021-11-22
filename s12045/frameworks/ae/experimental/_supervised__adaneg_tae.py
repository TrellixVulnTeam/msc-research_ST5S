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

import logging
from dataclasses import dataclass
from numbers import Number
from typing import Any
from typing import Dict
from typing import Sequence
from typing import Tuple
from typing import Union

import torch

from s12045.frameworks.ae._supervised__tae import TripletAe
from s12045.frameworks.ae.experimental._weaklysupervised__adaae import AdaAe
from s12045.frameworks.vae.experimental._supervised__adaneg_tvae import AdaNegTripletVae


log = logging.getLogger(__name__)


# ========================================================================= #
# Guided Ada Vae                                                            #
# ========================================================================= #


class AdaNegTripletAe(TripletAe):
    """
    This is a condensed version of the ada_tvae and adaave_tvae,
    using approximately the best settings and loss...
    """

    REQUIRED_OBS = 3

    @dataclass
    class cfg(TripletAe.cfg, AdaAe.cfg):
        # ada_tvae - loss
        adat_triplet_share_scale: float = 0.95

    def hook_ae_compute_ave_aug_loss(self, zs: Sequence[torch.Tensor], xs_partial_recon: Sequence[torch.Tensor], xs_targ: Sequence[torch.Tensor]) -> Tuple[Union[torch.Tensor, Number], Dict[str, Any]]:
        return AdaNegTripletVae.estimate_ada_triplet_loss_from_zs(
            zs=zs,
            cfg=self.cfg,
        )


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
