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

import numpy as np

from s12045.dataset.data import XYObjectData
from s12045.dataset.data import XYObjectShadedData
from s12045.dataset.data import XYSquaresData         # pragma: delete-on-release
from s12045.dataset.data import XYSquaresMinimalData  # pragma: delete-on-release


# ========================================================================= #
# TESTS                                                                     #
# ========================================================================= #


def test_xysquares_similarity():                      # pragma: delete-on-release
    data_org = XYSquaresData()                        # pragma: delete-on-release
    data_min = XYSquaresMinimalData()                 # pragma: delete-on-release
    # check lengths                                   # pragma: delete-on-release
    assert len(data_org) == len(data_min)             # pragma: delete-on-release
    n = len(data_min)                                 # pragma: delete-on-release
    # check items                                     # pragma: delete-on-release
    for i in np.random.randint(0, n, size=100):       # pragma: delete-on-release
        assert np.allclose(data_org[i], data_min[i])  # pragma: delete-on-release
    # check bounds                                    # pragma: delete-on-release
    assert np.allclose(data_org[0], data_min[0])      # pragma: delete-on-release
    assert np.allclose(data_org[n-1], data_min[n-1])  # pragma: delete-on-release


def test_xyobject_similarity():
    for palette in XYObjectData.COLOR_PALETTES_3.keys():
        # create
        data0 = XYObjectData(palette=palette)
        data1 = XYObjectShadedData(palette=palette)
        assert len(data0) == len(data1)
        assert data0.factor_sizes == (*data1.factor_sizes[:-2], np.prod(data1.factor_sizes[-2:]))
        # check random
        for i in np.random.randint(len(data0), size=100):
            assert np.allclose(data0[i], data1[i])


def test_xyobject_grey_similarity():
    for palette in XYObjectData.COLOR_PALETTES_1.keys():
        # create
        data0 = XYObjectData(palette=palette, rgb=False)
        data1 = XYObjectShadedData(palette=palette, rgb=False)
        assert len(data0) == len(data1)
        assert data0.factor_sizes == (*data1.factor_sizes[:-2], np.prod(data1.factor_sizes[-2:]))
        # check random
        for i in np.random.randint(len(data0), size=100):
            assert np.allclose(data0[i], data1[i])


# ========================================================================= #
# END                                                                       #
# ========================================================================= #
