#!/bin/bash

# ========================================================================= #
# Settings                                                                  #
# ========================================================================= #

export USERNAME="n_michlo"
export PROJECT="final-01__incr-overlap"
export PARTITION="stampede"
export PARALLELISM=28

# source the helper file
source "$(dirname "$(dirname "$(realpath -s "$0")")")/helper.sh"

# ========================================================================= #
# Experiment                                                                #
# ========================================================================= #

# background launch various xysquares
# -- original experiment also had dfcvae
# 5 * (2*2*8 = 32) = 160
submit_sweep \
    +DUMMY.repeat=5 \
    +EXTRA.tags='sweep_xy_squares' \
    \
    run_length=medium \
    framework=betavae,adavae_os \
    \
    settings.framework.beta=0.0316 \
    settings.model.z_size=9,25 \
    \
    dataset=xysquares \
    dataset.data.grid_spacing=8,7,6,5,4,3,2,1

# background launch traditional datasets
# -- original experiment also had dfcvae
# 5 * (2*2*4 = 16) = 80
submit_sweep \
    +DUMMY.repeat=5 \
    +EXTRA.tags='sweep_other' \
    \
    run_length=medium \
    framework=betavae,adavae_os \
    \
    settings.framework.beta=0.0316 \
    settings.model.z_size=9,25 \
    \
    dataset=cars3d,shapes3d,dsprites,smallnorb
