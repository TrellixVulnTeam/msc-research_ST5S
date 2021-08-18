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

import hydra
import torch.utils.data
import pytorch_lightning as pl
from omegaconf import DictConfig

from disent.dataset import DisentDataset
from disent.nn.transform import DisentDatasetTransform
from experiment.util.hydra_utils import instantiate_recursive


# ========================================================================= #
# DISENT DATASET MODULE                                                     #
# TODO: possible implementation outline for disent                          #
# ========================================================================= #


# class DisentDatasetModule(pl.LightningDataModule):
#
#     def prepare_data(self, *args, **kwargs):
#         raise NotImplementedError
#
#     def setup(self, stage: Optional[str] = None):
#         raise NotImplementedError
#
#     # DATASET HANDLING
#
#     @property
#     def dataset_train(self) -> DisentDataset:
#         # this property should check `framework_applies_augment` to return the
#         # dataset with the correct transforms/augments applied.
#         # - train_dataloader() should create the DataLoader from this dataset object
#         raise NotImplementedError
#
#     # FRAMEWORK AUGMENTATION HANDLING
#
#     @property
#     def framework_applies_augment(self) -> bool:
#         # if we augment the data in the framework rather, we can augment on the GPU instead
#         # framework needs manual handling of this augmentation mode
#         raise NotImplementedError
#
#     def framework_augment(self, batch):
#         # the augment to be applied if `framework_applies_augment` is `True`, otherwise
#         # this method should do nothing!
#         raise NotImplementedError


# ========================================================================= #
# DATASET                                                                   #
# ========================================================================= #


class HydraDataModule(pl.LightningDataModule):

    def __init__(self, hparams: DictConfig):
        super().__init__()
        # support pytorch lightning < 1.4
        if not hasattr(self, 'hparams'):
            self.hparams = DictConfig(hparams)
        else:
            self.hparams.update(hparams)
        # transform: prepares data from datasets
        self.data_transform = instantiate_recursive(self.hparams.dataset.transform)
        assert (self.data_transform is None) or callable(self.data_transform)
        # input_transform_aug: augment data for inputs, then apply input_transform
        self.input_transform = instantiate_recursive(self.hparams.augment.transform)
        assert (self.input_transform is None) or callable(self.input_transform)
        # batch_augment: augments transformed data for inputs, should be applied across a batch
        # which version of the dataset we need to use if GPU augmentation is enabled or not.
        # - corresponds to below in train_dataloader()
        if self.hparams.dataset.gpu_augment:
            # TODO: this is outdated!
            self.batch_augment = DisentDatasetTransform(transform=self.input_transform)
        else:
            self.batch_augment = None
        # datasets initialised in setup()
        self.dataset_train_noaug: DisentDataset = None
        self.dataset_train_aug: DisentDataset = None

    def prepare_data(self) -> None:
        # *NB* Do not set model parameters here.
        # - Instantiate data once to download and prepare if needed.
        # - trainer.prepare_data_per_node affects this functions behavior per node.
        data = dict(self.hparams.dataset.data)
        if 'in_memory' in data:
            del data['in_memory']
        instantiate_recursive(data)

    def setup(self, stage=None) -> None:
        # ground truth data
        data = instantiate_recursive(self.hparams.dataset.data)
        # Wrap the data for the framework some datasets need triplets, pairs, etc.
        # Augmentation is done inside the frameworks so that it can be done on the GPU, otherwise things are very slow.
        self.dataset_train_noaug = DisentDataset(data, hydra.utils.instantiate(self.hparams.dataset_sampler.sampler), transform=self.data_transform, augment=None)
        self.dataset_train_aug = DisentDataset(data, hydra.utils.instantiate(self.hparams.dataset_sampler.sampler), transform=self.data_transform, augment=self.input_transform)
        # TODO: make these assertions more general with some base-class
        assert isinstance(self.dataset_train_noaug, DisentDataset)
        assert isinstance(self.dataset_train_aug, DisentDataset)

    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #
    # Training Dataset:
    #     The sample of data used to fit the model.
    # Validation Dataset:
    #     Data used to provide an unbiased evaluation of a model fit on the
    #     training dataset while tuning model hyperparameters. The
    #     evaluation becomes more biased as skill on the validation
    #     dataset is incorporated into the model configuration.
    # Test Dataset:
    #     The sample of data used to provide an unbiased evaluation of a
    #     final model fit on the training dataset.
    # - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - #

    def train_dataloader(self):
        """
        Training Dataset: Sample of data used to fit the model.
        """
        # Select which version of the dataset we need to use if GPU augmentation is enabled or not.
        # - corresponds to above in __init__()
        if self.hparams.dataset.gpu_augment:
            dataset = self.dataset_train_noaug
        else:
            dataset = self.dataset_train_aug
        # create dataloader
        return torch.utils.data.DataLoader(
            dataset=dataset,
            batch_size=self.hparams.dataset.batch_size,
            num_workers=self.hparams.dataset.num_workers,
            shuffle=True,
            # This should usually be TRUE if cuda is enabled.
            # About 20% faster with the xysquares dataset, RTX 2060 Rev. A, and Intel i7-3930K
            pin_memory=self.hparams.dataset.pin_memory,
        )
