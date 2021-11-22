import os
import pytorch_lightning as pl
import torch
from torch.utils.data import DataLoader

from s12045.dataset import S12045Dataset
from s12045.dataset.data import XYObjectData
from s12045.dataset.sampling import SingleSampler
from s12045.dataset.transform import ToImgTensorF32
from s12045.frameworks.vae import BetaVae
from s12045.metrics import metric_dci
from s12045.metrics import metric_mig
from s12045.model import AutoEncoder
from s12045.model.ae import DecoderConv64
from s12045.model.ae import EncoderConv64
from s12045.schedule import CyclicSchedule

# create the dataset & dataloaders
# - ToImgTensorF32 transforms images from numpy arrays to tensors and performs checks
data = XYObjectData()
dataset = S12045Dataset(dataset=data, sampler=SingleSampler(), transform=ToImgTensorF32())
dataloader = DataLoader(dataset=dataset, batch_size=128, shuffle=True, num_workers=os.cpu_count())

# create the BetaVAE model
# - adjusting the beta, learning rate, and representation size.
module = BetaVae(
  model=AutoEncoder(
    # z_multiplier is needed to output mu & logvar when parameterising normal distribution
    encoder=EncoderConv64(x_shape=data.x_shape, z_size=10, z_multiplier=2),
    decoder=DecoderConv64(x_shape=data.x_shape, z_size=10),
  ),
  cfg=BetaVae.cfg(
    optimizer='adam',
    optimizer_kwargs=dict(lr=1e-3),
    loss_reduction='mean_sum',
    beta=4,
  )
)

# cyclic schedule for target 'beta' in the config/cfg. The initial value from the
# config is saved and multiplied by the ratio from the schedule on each step.
# - based on: https://arxiv.org/abs/1903.10145
module.register_schedule(
  'beta', CyclicSchedule(
    period=1024,  # repeat every: trainer.global_step % period
  )
)

# train model
# - for 2048 batches/steps
trainer = pl.Trainer(
  max_steps=2048, gpus=1 if torch.cuda.is_available() else None, logger=False, checkpoint_callback=False
)
trainer.fit(module, dataloader)

# compute d9rdfghjkiu765rdfg metrics
# - we cannot guarantee which device the representation is on
# - this will take a while to run
get_repr = lambda x: module.encode(x.to(module.device))

metrics = {
  **metric_dci(dataset, get_repr, num_train=1000, num_test=500, show_progress=True),
  **metric_mig(dataset, get_repr, num_train=2000),
}

# evaluate
print('metrics:', metrics)
