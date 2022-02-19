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

import logging
import warnings
from typing import List
from typing import Union

import numpy as np
import scipy.stats
import torch
from PIL import Image

from disent.util import to_numpy


log = logging.getLogger(__name__)


# ========================================================================= #
# operations on Images/Animations                                           #
# ========================================================================= #


# get bg color -- TODO: add support for more
_BG_COLOR_DTYPE_MAP = {
    'uint8':   127, np.uint8:   127, torch.uint8:   127, np.dtype('uint8'):   127,
    'float16': 0.5, np.float16: 0.5, torch.float16: 0.5, np.dtype('float16'): 0.5,
    'float32': 0.5, np.float32: 0.5, torch.float32: 0.5, np.dtype('float32'): 0.5,
    'float64': 0.5, np.float64: 0.5, torch.float64: 0.5, np.dtype('float64'): 0.5,
}


def make_image_grid(images, pad=8, border=True, bg_color=None, num_cols=None):
    """
    Convert a list of images into a single image that is a grid of those images.
    :param images: list of input images, all the same size: (I, H, W, C) or (I, H, W)
    :param pad: the number of pixels between images
    :param border: if there should be a border around the grid
    :param bg_color: the background color to use for padding (can be a float, int or RGB tuple)
    :param num_cols: the number of output columns in the grid. None for auto square, -1 for rows==1, or > 0 for that many cols.
    :return: single output image:  (H', W') or (H', W', C)
    """
    # first, second, third channels are the (H, W, C)
    # get image sizes
    img_shape, ndim = np.array(images[0].shape), images[0].ndim
    assert ndim == 2 or ndim == 3, 'images have wrong number of channels'
    assert np.all(img_shape == img.shape for img in images), 'Images are not the same shape!'
    # get image size and channels
    img_size = img_shape[:2]
    if ndim == 3:
        assert (img_shape[2] == 1) or (img_shape[2] == 3), 'Invalid number of channels for an image.'
    # get bg color
    if bg_color is None:
        bg_color = _BG_COLOR_DTYPE_MAP[images[0].dtype]
    # grid sizes
    num_rows, num_cols = _get_grid_size(len(images), num_cols=num_cols)
    grid_size = (img_size + pad) * [num_rows, num_cols] + (pad if border else -pad)
    # image sizes including padding on one side
    deltas = img_size + pad
    offset = pad if border else 0
    # make image
    grid = np.full_like(images, fill_value=bg_color, shape=(*grid_size, *img_shape[2:]))
    # fill image
    for i, img in enumerate(images):
        y0, x0 = offset + deltas * [i // num_cols, i % num_cols]
        y1, x1 = img_size + [y0, x0]
        grid[y0:y1, x0:x1, ...] = img
    return grid


def make_animated_image_grid(list_of_animated_images, pad=8, border=True, bg_color=None, num_cols=None):
    """
    :param list_of_animated_images: list of input images, with the second dimension the number of frames: : (I, F, H, W, C) or (I, F, H, W)
    :param pad: the number of pixels between images
    :param border: if there should be a border around the grid
    :param bg_color: the background color to use for padding (can be a float, int or RGB tuple)
    :param num_cols: the number of output columns in the grid. None for auto square, -1 for rows==1, or > 0 for that many cols.
    :return: animated output image: (F, H', W') or (F, H', W', C)
    """
    # first channel is the image (I)
    # second channel is the frame (F)
    # third, fourth, fifth channels are the (H, W, C)
    # -- (I, F, H, W, C)
    frames = []
    for list_of_images in zip(*list_of_animated_images):
        frames.append(make_image_grid(list_of_images, pad=pad, border=border, bg_color=bg_color, num_cols=num_cols))
    return to_numpy(frames)


# ========================================================================= #
# Calculations/Heuristics                                                   #
# ========================================================================= #


def _get_grid_size(n, num_cols=None):
    """
    Determine the number of rows and columns, given the total number of elements n.
    - if num_cols is None:     rows x cols is as square as possible
    - if num_cols is a number: minimum number of rows needed is returned.
    - if num_cols <= 0:        only 1 row is returned
    :return: (num_rows, num_cols)
    """
    if num_cols is None:
        num_cols = int(np.ceil(n ** 0.5))
    elif num_cols <= 0:
        num_cols = n
    num_rows = (n + num_cols - 1) // num_cols
    return num_rows, num_cols


# ========================================================================= #
# Factor Cycle Generators                                                   #
# ========================================================================= #


def _get_interval_factor_traversal(factor_size, num_frames, start_index=0):
    """
    Cycles through the state space in a single cycle.
    eg. num_indices=5, num_frames=7 returns: [0,1,1,2,3,3,4]
    eg. num_indices=4, num_frames=7 returns: [0,0,1,2,2,2,3]  # TODO: this result is weird
    """
    grid = np.linspace(0, factor_size - 1, num=num_frames, endpoint=True)
    grid = np.int64(np.around(grid))
    grid = (start_index + grid) % factor_size
    return grid


def _get_cycle_factor_traversal(factor_size, num_frames):
    """
    Cycles through the state space in a single cycle.
    eg. num_indices=5, num_frames=7 returns: [0,1,3,4,3,2,1]
    eg. num_indices=4, num_frames=7 returns: [0,1,2,3,2,2,0]
    """
    grid = _get_interval_factor_traversal(factor_size=factor_size, num_frames=num_frames)
    grid = np.concatenate([grid[0::2], grid[1::2][::-1]])
    return grid


_FACTOR_TRAVERSALS = {
    'interval': _get_interval_factor_traversal,
    'cycle': _get_cycle_factor_traversal,
}


def get_idx_traversal(factor_size, num_frames, mode='interval'):
    try:
        traversal_fn = _FACTOR_TRAVERSALS[mode]
    except KeyError:
        raise KeyError(f'Invalid factor traversal mode: {repr(mode)}')
    return traversal_fn(factor_size=factor_size, num_frames=num_frames)


# ========================================================================= #
# Cycle Generators | FROM: disentanglement_lib                              #
# ========================================================================= #


def cycle_gaussian(starting_value, num_frames, loc=0., scale=1.):
    """
    Cycles through the quantiles of a Gaussian in a single cycle.
    # ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~ #
    Copyright 2018 The DisentanglementLib Authors. All rights reserved.
    Licensed under the Apache License, Version 2.0
    https://github.com/google-research/disentanglement_lib
    # ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~ #
    """
    starting_prob = scipy.stats.norm.cdf(starting_value, loc=loc, scale=scale)
    grid = np.linspace(starting_prob, starting_prob + 2., num=num_frames, endpoint=False)
    grid -= np.maximum(0, 2 * grid - 2)
    grid += np.maximum(0, -2 * grid)
    grid = np.minimum(grid, 0.999)
    grid = np.maximum(grid, 0.001)
    return np.array([scipy.stats.norm.ppf(i, loc=loc, scale=scale) for i in grid])


def cycle_interval(starting_value, num_frames, min_val, max_val):
    """
    Cycles through the state space in a single cycle.
    # ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~ #
    Copyright 2018 The DisentanglementLib Authors. All rights reserved.
    Licensed under the Apache License, Version 2.0
    https://github.com/google-research/disentanglement_lib
    # ~=~=~=~=~=~=~=~=~=~=~=~=~=~=~=~ #
    """
    starting_in_01 = (starting_value - min_val) / (max_val - min_val)
    starting_in_01 = np.nan_to_num(starting_in_01)  # handle division by zero, prints warning
    grid = np.linspace(starting_in_01, starting_in_01 + 2., num=num_frames, endpoint=False)
    grid -= np.maximum(0, 2 * grid - 2)
    grid += np.maximum(0, -2 * grid)
    return grid * (max_val - min_val) + min_val


# ========================================================================= #
# Conversion/Util                                                           #
# ========================================================================= #


# TODO: this functionality is duplicated elsewhere!
# TODO: similar functions exist: output_image, to_img, to_imgs, reconstructions_to_images
def reconstructions_to_images(
    recon,
    mode: str = 'float',
    moveaxis: bool = True,
    recon_min: Union[float, List[float]] = 0.0,
    recon_max: Union[float, List[float]] = 1.0,
    warn_if_clipped: bool = True,
) -> Union[np.ndarray, Image.Image]:
    """
    Convert a batch of reconstructions to images.
    A batch in this case consists of an arbitrary number of dimensions of an array,
    with the last 3 dimensions making up the actual image. For example: (..., channels, size, size)

    NOTE: This function might not be efficient for large amounts of
          data due to assertions and initial recursive conversions to a numpy array.

    NOTE: kornia has a similar function!
    """
    img = to_numpy(recon)
    # checks
    assert img.ndim >= 3
    assert img.dtype in (np.float32, np.float64)
    # move channels axis
    if moveaxis:
        img = np.moveaxis(img, -3, -1)
    # check min and max
    recon_min = np.array(recon_min)
    recon_max = np.array(recon_max)
    assert recon_min.shape == recon_max.shape
    assert recon_min.ndim in (0, 1)  # supports channels or glbal min . max
    # scale image
    img = (img - recon_min) / (recon_max - recon_min)
    # check image bounds
    if warn_if_clipped:
        m, M = np.min(img), np.max(img)
        if m < 0 or M > 1:
            log.warning(f'images with range [{m}, {M}] have been clipped to the range [0, 1]')
    # do clipping
    img = np.clip(img, 0, 1)
    # convert
    if mode == 'float':
        return img
    elif mode == 'int':
        return np.uint8(img * 255)
    elif mode == 'pil':
        img = np.uint8(img * 255)
        # all the cases (even ndim == 3)... bravo numpy, bravo!
        images = [Image.fromarray(img[idx]) for idx in np.ndindex(img.shape[:-3])]
        images = np.array(images, dtype=object).reshape(img.shape[:-3])
        return images
    else:
        raise KeyError(f'Invalid mode: {repr(mode)} not in { {"float", "int", "pil"} }')


# ========================================================================= #
# END                                                                      #
# ========================================================================= #
