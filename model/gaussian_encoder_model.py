# from torch import nn
import torch
from torch import Tensor
import abc


# ========================================================================= #
# utility                                                                   #
# ========================================================================= #


# class View(torch.nn.Module):
#     """
#     Torch view/reshape layer
#     https://github.com/1Konny/Beta-VAE/blob/master/model.py
#     """
#
#     def __init__(self, size):
#         super(View, self).__init__()
#         self.size = size
#
#     def forward(self, tensor):
#         return tensor.view(self.size)


# ========================================================================= #
# gaussian encoder model                                                    #
# ========================================================================= #


class GaussianEncoderModel(torch.nn.Module, metaclass=abc.ABCMeta):

    def __init__(self, gaussian_encoder: torch.nn.Module, decoder: torch.nn.Module):
        super().__init__()
        self.gaussian_encoder = gaussian_encoder
        self.decoder = decoder

    def forward(self, x: Tensor) -> (Tensor, Tensor, Tensor, Tensor):
        """
        reconstruct the input:
        x -> encode  | z_mean, z_var
          -> z       | z ~ p(z|x)
          -> decode  |
          -> x_recon | no final activation
        """
        # encode
        z_mean, z_logvar = self.gaussian_encode(x.view(-1, self.x_dim))
        z = self.sample_from_latent_distribution(z_mean, z_logvar)
        # decode
        x_recon = self.decode(z).view(x.size())
        return x_recon, z_mean, z_logvar, z

    @staticmethod
    def sample_from_latent_distribution(z_mean: Tensor, z_logvar: Tensor) -> Tensor:
        """
        Randomly sample for z based on the parametrization of the gaussian normal with diagonal covariance.
        This is an implementation of the 'reparametrisation trick'.
        ie. z ~ p(z|x)
        Gaussian Encoder Model Distribution - pg. 25 in Variational Auto Encoders
        """
        std = torch.exp(0.5 * z_logvar)  # std == var^0.5 == e^(log(var^0.5)) == e^(0.5*log(var))
        eps = torch.randn_like(std)      # N(0, 1)
        return z_mean + (std * eps)      # mu + dot(std, eps)

    def gaussian_encode(self, x: Tensor) -> (Tensor, Tensor):
        """
        Compute the mean and logvar parametrisation for the gaussian
        normal distribution with diagonal covariance ie. the parametrisation for p(z|x).
        """
        z_mean, z_logvar = self.gaussian_encoder(x)
        return z_mean, z_logvar

    def decode(self, z: Tensor) -> Tensor:
        """
        Compute the partial reconstruction of the input from a latent vector.

        The final activation should not be included. This will always be sigmoid
        and is computed as part of the loss to improve numerical stability.
        """
        x_recon = self.decoder(z)
        return x_recon

    def reconstruct(self, z: Tensor) -> Tensor:
        """
        Compute the full reconstruction of the input from a latent vector.

        Like decode but performs a final sigmoid activation.
        """

        return torch.sigmoid(self.decode(z))


# ========================================================================= #
# END                                                                       #
# ========================================================================= #

