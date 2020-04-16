
# Make datasets directly accessible
from .shapes3d import Shapes3dDataset
from .xygrid import XYDataset


# ========================================================================= #
# shapes3d                                                                   #
# ========================================================================= #


def split_dataset(dataset, train_ratio=0.8):
    """
    splits a dataset randomly into a training (train_ratio) and test set (1-train_ratio).
    """
    import torch.utils.data
    train_size = int(train_ratio * len(dataset))
    test_size = len(dataset) - train_size
    return torch.utils.data.random_split(dataset, [train_size, test_size])


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
