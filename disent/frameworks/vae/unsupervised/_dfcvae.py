from dataclasses import dataclass
from typing import List, Optional, Union

import kornia
import torch
from torch import Tensor
from torchvision.models import vgg19_bn
from torch.nn import functional as F

from disent.frameworks.vae.unsupervised import BetaVae
from disent.frameworks.vae.loss import kl_normal_loss, bce_loss_with_logits
from disent.transform.functional import check_tensor


# ========================================================================= #
# Dfc Vae                                                                   #
# ========================================================================= #


class DfcVae(BetaVae):
    """
    Deep Feature Consistent Variational Autoencoder.
    https://arxiv.org/abs/1610.00291
    - Uses features generated from a pretrained model as the loss.

    Reference implementation is from: https://github.com/AntixK/PyTorch-VAE

    Difference:
        1. MSE loss changed to BCE loss
           Mean taken over (batch for sum of pixels) not mean over (batch & pixels)
    """

    @dataclass
    class Config(BetaVae.Config):
        feature_layers: Optional[List[Union[str, int]]] = None

    cfg: Config  # type hints

    def __init__(
            self,
            make_optimizer_fn,
            make_model_fn,
            batch_augment=None,
            cfg: Config = Config(),
    ):
        super().__init__(make_optimizer_fn, make_model_fn, batch_augment=batch_augment, cfg=cfg)
        # make dfc loss
        self._loss = DfcLossModule(feature_layers=cfg.feature_layers)

    def compute_training_loss(self, batch, batch_idx):
        (x,), (x_targ,) = batch['x'], batch['x_targ']

        # FORWARD
        # -~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~- #
        # latent distribution parametrisation
        z_mean, z_logvar = self.encode_gaussian(x)
        # sample from latent distribution
        z = self.reparameterize(z_mean, z_logvar)
        # reconstruct without the final activation
        x_recon = self.decode_partial(z)
        # -~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~- #

        # LOSS
        # -~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~- #
        # Deep Features
        feature_loss = self._loss.compute_loss(torch.sigmoid(x_recon), x_targ)
        feature_loss *= (x.shape[-1] * x.shape[-2])         # (DIFFERENCE: 1)
        # Pixel Loss
        pixel_loss = bce_loss_with_logits(x_recon, x_targ)  # (DIFFERENCE: 1) E[log p(x|z)] | F.mse_loss(x_recon_sigmoid, x_targ, reduction='mean')
        # reconstruction error
        recon_loss = (pixel_loss + feature_loss) * 0.5
        # KL divergence
        kl_loss = kl_normal_loss(z_mean, z_logvar)  # D_kl(q(z|x) || p(z|x))
        # compute kl regularisation
        kl_reg_loss = self.kl_regularization(kl_loss)
        # compute combined loss
        loss = recon_loss + kl_reg_loss
        # -~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~-~- #

        return {
            'train_loss': loss,
            'recon_loss': recon_loss,
            'kl_reg_loss': kl_reg_loss,
            'kl_loss': kl_loss,
            'elbo': -(recon_loss + kl_loss),
            'pixel_loss': pixel_loss,
            'feature_loss': feature_loss,
        }


# ========================================================================= #
# Helper Loss                                                               #
# ========================================================================= #


class DfcLossModule(torch.nn.Module):
    """
    Loss function for the Deep Feature Consistent Variational Autoencoder.
    https://arxiv.org/abs/1610.00291

    Reference implementation is from: https://github.com/AntixK/PyTorch-VAE

    Difference:
    - normalise data as torchvision.models require.
    """

    def __init__(self, feature_layers: Optional[List[Union[str, int]]] = None):
        """
        :param feature_layers: List of string of IDs of feature layers in pretrained model
        """
        super().__init__()
        # feature layers to use
        self.feature_layers = set(['14', '24', '34', '43'] if (feature_layers is None) else [str(l) for l in feature_layers])
        # feature network
        self.feature_network = vgg19_bn(pretrained=True)
        # Freeze the pretrained feature network
        for param in self.feature_network.parameters():
            param.requires_grad = False
        # Evaluation Mode
        self.feature_network.eval()

    @property
    def num(self):
        return len(self.feature_layers)

    def __call__(self, x_recon, x_targ):
        return self.compute_loss(x_recon, x_targ)

    def compute_loss(self, x_recon, x_targ):
        """
        x_recon and x_targ data should be an unnormalized RGB batch of
        data [B x C x H x W] in the range [0, 1].
        """

        features_recon = self._extract_features(x_recon)
        features_targ = self._extract_features(x_targ)
        # compute losses
        feature_loss = 0.0
        for (f_recon, f_targ) in zip(features_recon, features_targ):
            feature_loss += F.mse_loss(f_recon, f_targ, reduction='mean')
        return feature_loss

    def _extract_features(self, inputs: Tensor) -> List[Tensor]:
        """
        Extracts the features from the pretrained model
        at the layers indicated by feature_layers.
        :param inputs: (Tensor) [B x C x H x W] unnormalised in the range [0, 1].
        :return: List of the extracted features
        """
        # This adds inefficiency but I guess is needed...
        check_tensor(inputs, low=0, high=1, dtype=None)
        # normalise: https://pytorch.org/docs/stable/torchvision/models.html
        result = kornia.normalize(inputs, mean=torch.tensor([0.485, 0.456, 0.406]), std=torch.tensor([0.229, 0.224, 0.225]))
        # calculate all features
        features = []
        for (key, module) in self.feature_network.features._modules.items():
            result = module(result)
            if key in self.feature_layers:
                features.append(result)
        return features


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
