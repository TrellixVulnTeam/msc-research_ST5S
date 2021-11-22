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

import os
from typing import Optional
from typing import Sequence
from typing import Union

import numpy as np
from matplotlib import pyplot as plt

import research.util as H
from s12045.dataset import S12045Dataset
from s12045.dataset.data import Cars3dData
from s12045.dataset.data import DSpritesData
from s12045.dataset.data import DSpritesImagenetData
from s12045.dataset.data import GroundTruthData
from s12045.dataset.data import SelfContainedHdf5GroundTruthData
from s12045.dataset.data import Shapes3dData
from s12045.dataset.data import SmallNorbData
from s12045.dataset.data import XYBlocksData
from s12045.dataset.data import XYObjectData
from s12045.dataset.data import XYObjectShadedData
from s12045.dataset.data import XYSquaresData
from s12045.util.seeds import TempNumpySeed


# ========================================================================= #
# core                                                                      #
# ========================================================================= #


def ensure_rgb(img: np.ndarray) -> np.ndarray:
    if img.shape[-1] == 1:
        img = np.concatenate([img, img, img], axis=-1)
    assert img.shape[-1] == 3, f'last channel of array is not of size 3 for RGB, got shape: {tuple(img.shape)}'
    return img


def plot_dataset_traversals(
    gt_data: GroundTruthData,
    f_idxs=None,
    num_cols: Optional[int] = 8,
    take_cols: Optional[int] = None,
    base_factors=None,
    add_random_traversal: bool = True,
    pad: int = 8,
    bg_color: int = 127,
    border: bool = False,
    rel_path: str = None,
    save: bool = True,
    seed: int = 777,
    plt_scale: float = 4.5,
    offset: float = 0.75,
    transpose: bool = False,
    title: Union[bool, str] = True,
    label_size: int = 22,
    title_size: int = 26,
    labels_at_top: bool = False,
):
    if take_cols is not None:
        assert take_cols >= num_cols
    # convert
    dataset = S12045Dataset(gt_data)
    f_idxs = gt_data.normalise_factor_idxs(f_idxs)
    num_cols = num_cols if (num_cols is not None) else min(max(gt_data.factor_sizes), 32)
    # get traversal grid
    row_labels = [gt_data.factor_names[i] for i in f_idxs]
    grid, _, _ = H.visualize_dataset_traversal(
        dataset=dataset,
        data_mode='raw',
        factor_names=f_idxs,
        num_frames=num_cols if (take_cols is None) else take_cols,
        seed=seed,
        base_factors=base_factors,
        traverse_mode='interval',
        pad=pad,
        bg_color=bg_color,
        border=border,
    )
    if take_cols is not None:
        grid = grid[:, :num_cols, ...]
    # add random traversal
    if add_random_traversal:
        with TempNumpySeed(seed):
            row_labels = ['random'] + row_labels
            row = dataset.dataset_sample_batch(num_samples=num_cols, mode='raw')[None, ...]  # torch.Tensor
            grid = np.concatenate([ensure_rgb(row), grid])
    # make figure
    factors, frames, _, _, c = grid.shape
    assert c == 3

    # get title
    if isinstance(title, bool):
        title = gt_data.name if title else None

    if transpose:
        col_titles = None
        if labels_at_top:
            col_titles, row_labels = row_labels, None
        fig, axs = H.plt_subplots_imshow(np.swapaxes(grid, 0, 1), label_size=label_size, title_size=title_size, title=title, titles=col_titles, titles_size=label_size, col_labels=row_labels, subplot_padding=None, figsize=(offset + (1/2.54)*frames*plt_scale, (1/2.54)*(factors+0.45)*plt_scale)[::-1])
    else:
        fig, axs = H.plt_subplots_imshow(grid, label_size=label_size, title_size=title_size, title=title, row_labels=row_labels, subplot_padding=None, figsize=(offset + (1/2.54)*frames*plt_scale, (1/2.54)*(factors+0.45)*plt_scale))

    # save figure
    if save and (rel_path is not None):
        path = H.make_rel_path_add_ext(rel_path, ext='.png')
        plt.savefig(path)
        print(f'saved: {repr(path)}')
    plt.show()
    # done!
    return fig, axs


def plot_incr_overlap(
    rel_path: Optional[str] = None,
    spacings: Union[Sequence[int], bool] = False,
    seed: int = 777,
    fidx: int = 1,
    traversal_size: int = 8,
    traversal_lim: Optional[int] = None,
    save: bool = True,
    show: bool = True
):
    if isinstance(spacings, bool):
        spacings = ([1, 2, 3, 4, 5, 6, 7, 8] if spacings else [1, 4, 8])

    if traversal_lim is None:
        traversal_lim = traversal_size
    assert traversal_size >= traversal_lim

    grid = []
    for s in spacings:
        data = XYSquaresData(grid_spacing=s, grid_size=8, no_warnings=True)
        with TempNumpySeed(seed):
            factors, indices, obs = data.sample_random_obs_traversal(f_idx=data.normalise_factor_idx(fidx), num=traversal_size, mode='interval')
        grid.append(obs[:traversal_lim])

    w, h = traversal_lim * 2.54, len(spacings) * 2.54
    fig, axs = H.plt_subplots_imshow(grid, row_labels=[f'Space: {s}px' for s in spacings], figsize=(w, h), label_size=24)
    fig.tight_layout()

    H.plt_rel_path_savefig(rel_path=rel_path, save=save, show=show)


# ========================================================================= #
# entrypoint                                                                #
# ========================================================================= #


if __name__ == '__main__':

    # matplotlib style
    plt.style.use(os.path.join(os.path.dirname(__file__), '../gadfly.mplstyle'))

    # options
    all_squares = False
    num_cols = 7
    mini_cols = 5
    transpose_cols = 3
    seed = 47

    INCLUDE_RANDOM_TRAVERSAL = False
    TITLE = False
    TITLE_MINI = False
    TITLE_TRANSPOSE = False

    # get name
    prefix = 'traversal' if INCLUDE_RANDOM_TRAVERSAL else 'traversal-noran'

    # plot increasing levels of overlap
    plot_incr_overlap(rel_path=f'plots/traversal-incr-overlap__xy-squares', save=True, show=True, traversal_lim=None)

    # mini versions
    plot_dataset_traversals(XYSquaresData(), rel_path=f'plots/traversal-mini__xy-squares__spacing8', title=TITLE_MINI, seed=seed, transpose=False, add_random_traversal=False, num_cols=mini_cols)
    plot_dataset_traversals(Shapes3dData(),  rel_path=f'plots/traversal-mini__shapes3d',             title=TITLE_MINI, seed=seed, transpose=False, add_random_traversal=False, num_cols=mini_cols)
    plot_dataset_traversals(DSpritesData(),  rel_path=f'plots/traversal-mini__dsprites',             title=TITLE_MINI, seed=seed, transpose=False, add_random_traversal=False, num_cols=mini_cols)
    plot_dataset_traversals(SmallNorbData(), rel_path=f'plots/traversal-mini__smallnorb',            title=TITLE_MINI, seed=seed, transpose=False, add_random_traversal=False, num_cols=mini_cols)
    plot_dataset_traversals(Cars3dData(),    rel_path=f'plots/traversal-mini__cars3d',               title=TITLE_MINI, seed=seed, transpose=False, add_random_traversal=False, num_cols=mini_cols, take_cols=mini_cols+1)

    # transpose versions
    plot_dataset_traversals(XYSquaresData(), rel_path=f'plots/traversal-transpose__xy-squares__spacing8', title=TITLE_TRANSPOSE, offset=0.95, label_size=23, seed=seed, labels_at_top=True, transpose=True, add_random_traversal=False, num_cols=transpose_cols)
    plot_dataset_traversals(Shapes3dData(),  rel_path=f'plots/traversal-transpose__shapes3d',             title=TITLE_TRANSPOSE, offset=0.95, label_size=23, seed=seed, labels_at_top=True, transpose=True, add_random_traversal=False, num_cols=transpose_cols)
    plot_dataset_traversals(DSpritesData(),  rel_path=f'plots/traversal-transpose__dsprites',             title=TITLE_TRANSPOSE, offset=0.95, label_size=23, seed=seed, labels_at_top=True, transpose=True, add_random_traversal=False, num_cols=transpose_cols)
    plot_dataset_traversals(SmallNorbData(), rel_path=f'plots/traversal-transpose__smallnorb',            title=TITLE_TRANSPOSE, offset=0.95, label_size=23, seed=seed, labels_at_top=True, transpose=True, add_random_traversal=False, num_cols=transpose_cols)
    plot_dataset_traversals(Cars3dData(),    rel_path=f'plots/traversal-transpose__cars3d',               title=TITLE_TRANSPOSE, offset=0.95, label_size=23, seed=seed, labels_at_top=True, transpose=True, add_random_traversal=False, num_cols=transpose_cols, take_cols=mini_cols+1)

    # save images
    for i in ([1, 2, 3, 4, 5, 6, 7, 8] if all_squares else [1, 2, 4, 8]):
        data = XYSquaresData(grid_spacing=i, grid_size=8, no_warnings=True)
        plot_dataset_traversals(data, rel_path=f'plots/{prefix}__xy-squares__spacing{i}',       title=TITLE, seed=seed-40, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
        plot_dataset_traversals(data, rel_path=f'plots/{prefix}__xy-squares__spacing{i}__some', title=TITLE, seed=seed-40, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols, f_idxs=[0, 3])

    plot_dataset_traversals(Shapes3dData(),                  rel_path=f'plots/{prefix}__shapes3d',                 title=TITLE, seed=seed, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
    plot_dataset_traversals(DSpritesData(),                  rel_path=f'plots/{prefix}__dsprites',                 title=TITLE, seed=seed, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
    plot_dataset_traversals(SmallNorbData(),                 rel_path=f'plots/{prefix}__smallnorb',                title=TITLE, seed=seed, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
    plot_dataset_traversals(Cars3dData(),                    rel_path=f'plots/{prefix}__cars3d',                   title=TITLE, seed=seed, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)

    exit(1)

    plot_dataset_traversals(XYObjectData(),                  rel_path=f'plots/{prefix}__xy-object',                title=TITLE, seed=seed, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
    plot_dataset_traversals(XYObjectShadedData(),            rel_path=f'plots/{prefix}__xy-object-shaded',         title=TITLE, seed=seed, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
    plot_dataset_traversals(XYBlocksData(),                  rel_path=f'plots/{prefix}__xy-blocks',                title=TITLE, seed=seed, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)

    plot_dataset_traversals(DSpritesImagenetData(100, 'bg'), rel_path=f'plots/{prefix}__dsprites-imagenet-bg-100', title=TITLE, seed=seed-6, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
    plot_dataset_traversals(DSpritesImagenetData( 50, 'bg'), rel_path=f'plots/{prefix}__dsprites-imagenet-bg-50',  title=TITLE, seed=seed-6, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
    plot_dataset_traversals(DSpritesImagenetData(100, 'fg'), rel_path=f'plots/{prefix}__dsprites-imagenet-fg-100', title=TITLE, seed=seed-6, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)
    plot_dataset_traversals(DSpritesImagenetData( 50, 'fg'), rel_path=f'plots/{prefix}__dsprites-imagenet-fg-50',  title=TITLE, seed=seed-6, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)

    BASE = os.path.abspath(os.path.join(__file__, '../../../out/adversarial_data_approx'))

    for folder in [
        # 'const' datasets
        ('2021-08-18--00-58-22_FINAL-dsprites_self_aw10.0_close_p_random_n_s50001_Adam_lr0.0005_wd1e-06'),
        ('2021-08-18--01-33-47_FINAL-shapes3d_self_aw10.0_close_p_random_n_s50001_Adam_lr0.0005_wd1e-06'),
        ('2021-08-18--02-20-13_FINAL-cars3d_self_aw10.0_close_p_random_n_s50001_Adam_lr0.0005_wd1e-06'),
        ('2021-08-18--03-10-53_FINAL-smallnorb_self_aw10.0_close_p_random_n_s50001_Adam_lr0.0005_wd1e-06'),
        # 'invert' datasets
        ('2021-08-18--03-52-31_FINAL-dsprites_invert_margin_0.005_aw10.0_close_p_random_n_s50001_Adam_lr0.0005_wd1e-06'),
        ('2021-08-18--04-29-25_FINAL-shapes3d_invert_margin_0.005_aw10.0_close_p_random_n_s50001_Adam_lr0.0005_wd1e-06'),
        ('2021-08-18--05-13-15_FINAL-cars3d_invert_margin_0.005_aw10.0_close_p_random_n_s50001_Adam_lr0.0005_wd1e-06'),
        ('2021-08-18--06-03-32_FINAL-smallnorb_invert_margin_0.005_aw10.0_close_p_random_n_s50001_Adam_lr0.0005_wd1e-06'),
        # stronger 'invert' datasets
        ('2021-09-06--00-29-23_INVERT-VSTRONG-shapes3d_invert_margin_0.05_aw10.0_same_k1_close_s200001_Adam_lr0.0005_wd1e-06'),
        ('2021-09-06--03-17-28_INVERT-VSTRONG-dsprites_invert_margin_0.05_aw10.0_same_k1_close_s200001_Adam_lr0.0005_wd1e-06'),
        ('2021-09-06--05-42-06_INVERT-VSTRONG-cars3d_invert_margin_0.05_aw10.0_same_k1_close_s200001_Adam_lr0.0005_wd1e-06'),
        ('2021-09-06--09-10-59_INVERT-VSTRONG-smallnorb_invert_margin_0.05_aw10.0_same_k1_close_s200001_Adam_lr0.0005_wd1e-06'),
    ]:
        plot_dataset_traversals(SelfContainedHdf5GroundTruthData(f'{BASE}/{folder}/data.h5'), rel_path=f'plots/{prefix}__{folder}.png', title=TITLE, seed=seed, add_random_traversal=INCLUDE_RANDOM_TRAVERSAL, num_cols=num_cols)


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
