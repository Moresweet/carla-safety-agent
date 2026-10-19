"""Build the selected upstream voxel kernel in place without obsolete GPU targets."""
import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True, help='Explicit upstream model repository')
    args = parser.parse_args()
    training = args.root.resolve() / 'open_loop_training'
    sources = ['ops/voxel_pooling/src/voxel_pooling_forward.cpp',
               'ops/voxel_pooling/src/voxel_pooling_forward_cuda.cu']
    if not all((training / source).is_file() for source in sources):
        parser.error('Original voxel pooling sources are missing')
    if os.environ.get('TORCH_CUDA_ARCH_LIST') != '12.0':
        parser.error('This local build requires explicit TORCH_CUDA_ARCH_LIST=12.0')
    # Import before changing cwd: upstream's code/ would shadow stdlib code.
    import torch
    from setuptools import setup
    from torch.utils.cpp_extension import CUDAExtension, BuildExtension
    os.chdir(training)
    setup(name='opendrive-local-voxel',
          script_args=['build_ext', '--inplace'],
          ext_modules=[CUDAExtension('ops.voxel_pooling.voxel_pooling_ext', sources=sources,
              define_macros=[('WITH_CUDA', None)],
              extra_compile_args={'cxx': ['-std=c++17'], 'nvcc': ['-std=c++17',
                  '-D__CUDA_NO_HALF_OPERATORS__', '-D__CUDA_NO_HALF_CONVERSIONS__',
                  '-D__CUDA_NO_HALF2_OPERATORS__']})],
          cmdclass={'build_ext': BuildExtension})


if __name__ == '__main__':
    main()
