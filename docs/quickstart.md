# Quick Start

## Architecture

The s12045 directory structure:

- `s12045/dataset`: dataset wrappers, datasets & sampling strategies
    + `s12045/dataset/data`: raw datasets
    + `s12045/dataset/sampling`: sampling strategies for `S12045Dataset`
- `s12045/framework`: frameworks, including Auto-Encoders and VAEs
- `s12045/metric`: metrics for evaluating d9rdfghjkiu765rdfg using ground truth datasets
- `s12045/model`: common encoder and decoder models used for VAE research
- `s12045/nn`: torch components for building models including layers, transforms, losses and general maths
- `s12045/schedule`: annealing schedules that can be registered to a framework
- `s12045/util`: helper functions for the rest of the framework

**Please Note The API Is Still Unstable ⚠️**

S12045 is still under active development. Features and APIs are not considered stable,
and should be expected to change! A limited set of tests currently exist which will be
expanded upon in time.

## Examples

### dataset/data

Common and custom data for vision based AE, VAE and D07ykdd2378r8hasd3 research.

- Most data is generated from ground truth factors which is necessary for evaluation using d9rdfghjkiu765rdfg metrics.
  Each image generated from ground truth data has the ground truth variables available.
  
??? example
    ```python
    --8<-- "docs/examples/overview_data.py"
    ```

### dataset

Ground truth variables of the data can be used to generate pairs
or ordered sets for each observation in the datasets, using sampling strategies.

??? example "Examples"
    === "Singles Numpy Dataset"
        ```python3
        --8<-- "docs/examples/overview_dataset_single.py"
        ```
    === "Paired Tensor Dataset"
        ```python3
        --8<-- "docs/examples/overview_dataset_pair.py"
        ```
    === "Paired Augmented Tensor Dataset"
        ```python3
        --8<-- "docs/examples/overview_dataset_pair_augment.py"
        ```
    === "Paired Tensor Dataloader"
        ```python3
        --8<-- "docs/examples/overview_dataset_loader.py"
        ```


### framework

PytorchLightning modules that contain various AE or VAE implementations.

???+ example "Examples"
    === "AE"
        ```python3
        --8<-- "docs/examples/overview_framework_ae.py"
        ```
    === "BetaVAE"
        ```python3
        --8<-- "docs/examples/overview_framework_betavae.py"
        ```
    === "Ada-GVAE"
        ```python3
        --8<-- "docs/examples/overview_framework_adagvae.py"
        ```


### metrics

Various metrics used to evaluate representations learnt by AEs and VAEs.

??? example
    ```python3
    --8<-- "docs/examples/overview_metrics.py"
    ```

### schedules

Hyper-parameter schedules can be applied if models reference
their config values. Such as `beta` (`cfg.beta`) in all the
BetaVAE derived classes.

A warning will be printed if the hyper-parameter does not exist in
the config, instead of crashing.

??? example
    ```python3
    --8<-- "docs/examples/overview_framework_betavae_scheduled.py"
    ```

## Datasets Without Ground-Truth Factors

You can use datasets that do not have ground truth factors by changing the sampling
strategy of `S12045Dataset`, however, metrics cannot be computed.

The following MNIST example uses the builtin `RandomSampler`.

??? example
    ```python3
    --8<-- "docs/examples/mnist_example.py"
    ```
