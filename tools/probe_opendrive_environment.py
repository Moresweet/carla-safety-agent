"""Explicit isolated legacy-model dependency probe; never connects to CARLA."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path, required=True)
    parser.add_argument('--mmdet3d', type=Path, required=True)
    parser.add_argument('--native-ops', type=Path, required=True,
                        help='Existing compiled MMCV directory for this exact Python/Torch ABI; compatibility is tested, not assumed')
    parser.add_argument('--gpu-probe', action='store_true')
    parser.add_argument('--sparse-only', action='store_true', help='Probe spconv independently of unfinished MMCV integration')
    parser.add_argument('--extra-packages', type=Path, action='append', default=[])
    parser.add_argument('--voxel-pooling', type=Path,
                        help='Optional original open_loop_training directory; exercise its compiled pooling kernel')
    parser.add_argument('--thinktwice-root', type=Path)
    parser.add_argument('--checkpoint', type=Path)
    args = parser.parse_args()
    if args.voxel_pooling and (not args.gpu_probe or not args.voxel_pooling.is_dir()):
        parser.error('--voxel-pooling requires an existing directory and --gpu-probe')
    if bool(args.thinktwice_root) != bool(args.checkpoint) or (args.thinktwice_root and args.sparse_only):
        parser.error('Model construction requires --thinktwice-root and --checkpoint without --sparse-only')
    for path in (args.packages, args.mmdet3d, args.native_ops, *args.extra_packages):
        if not path.is_dir():
            parser.error('Dependency directory is missing: ' + str(path))
    sys.path[:0] = [*(str(p.resolve()) for p in args.extra_packages), str(args.packages.resolve()), str(args.mmdet3d.resolve())]
    report = {'ok': False, 'scope': 'Dependency imports, optional tiny GPU kernels and strict CPU model load; no model inference or CARLA',
              'world_modified': False, 'gpu_probe_requested': args.gpu_probe}
    try:
        import torch
        report.update(torch=torch.__version__, sparse_only=args.sparse_only)
        if not args.sparse_only:
            import mmcv
            if Path(mmcv.__file__).resolve().parent != args.packages.resolve() / 'mmcv':
                raise RuntimeError('Isolated MMCV was not selected')
            mmcv.__path__.append(str(args.native_ops.resolve()))
            import mmcv._ext
            import mmdet
            import mmseg
            import mmdet3d
            from mmdet3d.models import build_model
            from mmdet3d.ops.spconv import IS_SPCONV2_AVAILABLE
            report.update(mmcv=mmcv.__version__, mmdet=mmdet.__version__,
                          mmseg=mmseg.__version__, mmdet3d=mmdet3d.__version__,
                          native_ops=mmcv._ext.__file__, spconv2=IS_SPCONV2_AVAILABLE)
            if args.thinktwice_root:
                sys.path.insert(0, str(args.thinktwice_root.resolve()))
                importlib.import_module('open_loop_training.code')
                cfg = mmcv.Config.fromfile(str(args.thinktwice_root / 'open_loop_training/configs/thinktwice.py'))
                # Complete checkpoint coverage below is mandatory. Do not fetch
                # a second pretrained ResNet during construction or tolerate
                # random parameters left over from a non-strict load.
                cfg.model.img_encoder.img_backbone_conf.init_cfg = None
                model = build_model(cfg.model, train_cfg=cfg.get('train_cfg'), test_cfg=cfg.get('test_cfg'))
                checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
                state = checkpoint['state_dict']
                expected = model.state_dict()
                missing = sorted(set(expected) - set(state))
                unexpected = sorted(set(state) - set(expected))
                shapes = {k: {'expected': list(expected[k].shape), 'actual': list(state[k].shape)}
                          for k in set(expected) & set(state) if expected[k].shape != state[k].shape}
                report['checkpoint_coverage'] = {'missing': missing, 'unexpected': unexpected,
                                                 'shape_mismatches': shapes, 'entries': len(state)}
                if missing or unexpected or shapes:
                    raise RuntimeError('Checkpoint does not exactly cover constructed model; no inference allowed')
                model.load_state_dict(state, strict=True)
                with args.checkpoint.open('rb') as stream:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                report.update(checkpoint_sha256=digest.hexdigest(), model_loaded_strictly=True,
                              model_inference_tested=False)
        if args.gpu_probe:
            import spconv.pytorch as spconv
            report['sparse_gpu_checks'] = []
            for dtype in (torch.float32, torch.float16):
                features = torch.arange(64, device='cuda', dtype=dtype).reshape(2, 32)
                indices = torch.tensor([[0, 1, 1, 1], [0, 1, 1, 2]], dtype=torch.int32, device='cuda')
                sparse = spconv.SparseConvTensor(features, indices, [4, 4, 4], 1)
                # A 3x3x3 kernel actually exercises sparse neighbour discovery;
                # kernel size 1 could quietly reduce to ordinary dense matmul.
                conv = spconv.SubMConv3d(32, 32, 3, padding=1, bias=False).cuda().to(dtype).eval()
                with torch.no_grad():
                    conv.weight.fill_(1.)
                    actual = conv(sparse).features
                torch.cuda.synchronize()
                torch.testing.assert_close(actual, features.sum().expand(2, 32))
                report['sparse_gpu_checks'].append({'dtype': str(dtype), 'shape': list(actual.shape),
                                                   'value': actual[0, 0].item()})
            if args.voxel_pooling:
                # Import Torch before adding upstream's directory named code,
                # which would otherwise shadow Python's standard-library code.
                sys.path.insert(0, str(args.voxel_pooling.resolve()))
                from ops.voxel_pooling.voxel_pooling import voxel_pooling
                geom = torch.tensor([[[0, 0, 0], [0, 0, 1], [1, 1, 0], [-1, 0, 0], [2, 0, 0]]],
                                    dtype=torch.int32, device='cuda')
                features = torch.arange(10, dtype=torch.float32, device='cuda').reshape(1, 5, 2).requires_grad_()
                actual = voxel_pooling(geom, features, torch.tensor([2, 2, 2], dtype=torch.int32))
                expected = torch.tensor([[[[2., 0.], [0., 4.]], [[4., 0.], [0., 5.]]]], device='cuda')
                torch.testing.assert_close(actual, expected)
                actual.sum().backward()
                torch.testing.assert_close(features.grad, torch.tensor([[[1., 1.], [1., 1.], [1., 1.], [0., 0.], [0., 0.]]], device='cuda'))
                torch.cuda.synchronize()
                report['voxel_pooling_check'] = {'forward': True, 'backward': True,
                                               'duplicate_voxels_summed': True, 'out_of_bounds_ignored': True}
        report['ok'] = True
    except Exception as exc:
        report.update(error_type=type(exc).__name__, error=str(exc))
    print(json.dumps(report, indent=2))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
