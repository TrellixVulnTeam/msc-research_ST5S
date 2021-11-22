import os
import pytorch_lightning as pl
from torch.utils.data import DataLoader
from torchvision import datasets
from tqdm import tqdm
from s12045.dataset import DisentDataset
from s12045.dataset.sampling import RandomSampler
from s12045.frameworks.vae import AdaVae
from s12045.model import AutoEncoder
from s12045.model.ae import DecoderFC, EncoderFC
from s12045.dataset.transform import ToImgTensorF32


# modify the mnist dataset to only return images, not labels
class MNIST(datasets.MNIST):
    def __getitem__(self, index):
        img, target = super().__getitem__(index)
        return img


# make mnist dataset -- adjust num_samples here to match framework. TODO: add tests that can fail with a warning -- dataset downloading is not always reliable
data_folder   = os.path.abspath(os.path.join(__file__, '../data/dataset'))
dataset_train = DisentDataset(MNIST(data_folder, train=True,  download=True, transform=ToImgTensorF32()), sampler=RandomSampler(num_samples=2))
dataset_test  =               MNIST(data_folder, train=False, download=True, transform=ToImgTensorF32())

# create the dataloaders
dataloader_train = DataLoader(dataset=dataset_train, batch_size=128, shuffle=True, num_workers=os.cpu_count())
dataloader_test  = DataLoader(dataset=dataset_test,  batch_size=128, shuffle=True, num_workers=os.cpu_count())

# create the model
module = AdaVae(
    model=AutoEncoder(
        encoder=EncoderFC(x_shape=(1, 28, 28), z_size=9, z_multiplier=2),
        decoder=DecoderFC(x_shape=(1, 28, 28), z_size=9),
    ),
    cfg=AdaVae.cfg(
        optimizer='adam', optimizer_kwargs=dict(lr=1e-3),
        beta=4, recon_loss='mse', loss_reduction='mean_sum',  # "mean_sum" is the traditional loss reduction mode, rather than "mean"
    )
)

# train the model
trainer = pl.Trainer(logger=False, checkpoint_callback=False, max_steps=2048)  # callbacks=[VaeLatentCycleLoggingCallback(every_n_steps=250, plt_show=True)]
trainer.fit(module, dataloader_train)

# move back to gpu & manually encode some observation
for xs in tqdm(dataloader_test, desc='Custom Evaluation'):
    zs = module.encode(xs.to(module.device))
