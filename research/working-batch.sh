#!/bin/bash

# ========================================================================= #
# Settings                                                                  #
# ========================================================================= #

export PROJECT="N/A"
export USERNAME="N/A"
export PARTITION="batch"
export PARALLELISM=24

# source the helper file
source "$(dirname "$(realpath -s "$0")")/helper.sh"

# ========================================================================= #
# Experiment                                                                #
# ========================================================================= #

clog_cuda_nodes "$PARTITION" 43200 "W-s12045" # 12 hours
