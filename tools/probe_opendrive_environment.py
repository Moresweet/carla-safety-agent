"""Explicit isolated legacy-model dependency probe; never connects to CARLA."""
import argparse
import hashlib
import importlib
import logging
import os
import time
import traceback
import json
from pathlib import Path
import sys
from contextlib import nullcontext
from unittest.mock import patch


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
    parser.add_argument('--driveadapter-root', type=Path)
    parser.add_argument('--legacy-spconv-rsck', action='store_true', help='Explicit original DriveAdapter sparse weight layout, audited conversion to KRSC')
    parser.add_argument('--checkpoint', type=Path)
    parser.add_argument('--report', type=Path, help='Write a new JSON evidence file; never overwrite')
    parser.add_argument('--synthetic-forward', action='store_true',
                        help='Run the real loaded network on explicitly synthetic full-size tensors, not CARLA data')
    args = parser.parse_args()
    if args.report and (args.report.exists() or not args.report.parent.is_dir()):
        parser.error('--report must be a new file in an existing directory')
    if args.voxel_pooling and (not args.gpu_probe or not args.voxel_pooling.is_dir()):
        parser.error('--voxel-pooling requires an existing directory and --gpu-probe')
    if args.thinktwice_root and args.driveadapter_root:
        parser.error('Select exactly one model root per isolated process')
    model_root = args.thinktwice_root or args.driveadapter_root
    if args.legacy_spconv_rsck and not args.driveadapter_root:
        parser.error('--legacy-spconv-rsck requires the explicit DriveAdapter root')
    if bool(model_root) != bool(args.checkpoint) or (model_root and args.sparse_only):
        parser.error('Model construction requires --thinktwice-root and --checkpoint without --sparse-only')
    if args.synthetic_forward and (not model_root or not args.gpu_probe):
        parser.error('--synthetic-forward requires a model and --gpu-probe')
    if args.synthetic_forward and args.driveadapter_root and not args.legacy_spconv_rsck:
        parser.error('DriveAdapter synthetic forward requires audited --legacy-spconv-rsck conversion')
    for path in (args.packages, args.mmdet3d, args.native_ops, *args.extra_packages):
        if not path.is_dir():
            parser.error('Dependency directory is missing: ' + str(path))
    sys.path[:0] = [*(str(p.resolve()) for p in args.extra_packages), str(args.packages.resolve()), str(args.mmdet3d.resolve())]
    report = {'ok': False, 'scope': 'Isolated dependency/model probe; optional synthetic inference, never CARLA or closed-loop validation',
              'world_modified': False, 'gpu_probe_requested': args.gpu_probe}
    try:
        logging.disable(logging.INFO)
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
            if model_root:
                sys.path[:0] = [str(model_root.resolve()),
                                str(model_root.resolve() / 'open_loop_training')]
                importlib.import_module('open_loop_training.code')
                model_name = 'thinktwice' if args.thinktwice_root else 'driveadapter'
                cfg = mmcv.Config.fromfile(str(model_root / f'open_loop_training/configs/{model_name}.py'))
                report['model'] = model_name
                # Complete checkpoint coverage below is mandatory. Do not fetch
                # a second pretrained ResNet during construction or tolerate
                # random parameters left over from a non-strict load.
                cfg.model.img_encoder.img_backbone_conf.init_cfg = None
                initializer = nullcontext()
                if args.driveadapter_root:
                    head = importlib.import_module('open_loop_training.code.model_code.dense_heads.driver_adapter_head').DriveAdapterHead
                    # This constructor helper only writes Parameters. Full
                    # checkpoint coverage below must replace EVERY parameter
                    # and buffer before the model can pass. Never deserialize
                    # the ancillary legacy Gym checkpoint with unsafe pickle.
                    initializer = patch.object(head, 'load_roach_layers', lambda self, module_dict: None)
                    report['initialization_override'] = 'Skip auxiliary Roach parameter initialization only; mandatory strict complete DriveAdapter checkpoint coverage follows'
                with initializer:
                    model = build_model(cfg.model, train_cfg=cfg.get('train_cfg'), test_cfg=cfg.get('test_cfg'))
                checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=True)
                state = checkpoint['state_dict']
                if args.legacy_spconv_rsck:
                    from legacy_sparse_weights import convert_rsck_state
                    state, report['sparse_weight_conversion'] = convert_rsck_state(model, state)
                expected = model.state_dict()
                missing = sorted(set(expected) - set(state))
                unexpected = sorted(set(state) - set(expected))
                shapes = {k: {'expected': list(expected[k].shape), 'actual': list(state[k].shape)}
                          for k in set(expected) & set(state) if expected[k].shape != state[k].shape}
                report['checkpoint_coverage'] = {'missing': missing, 'unexpected': unexpected,
                                                 'shape_mismatches': shapes, 'entries': len(state)}
                if missing or unexpected or shapes:
                    raise RuntimeError('Checkpoint does not exactly cover constructed model; no inference allowed')
                if args.thinktwice_root:
                    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
                    from carla_safety_agent.strict_model_weights import load_complete_checkpoint
                    load_complete_checkpoint(model, args.checkpoint)
                    report['adapter_checkpoint_loader'] = model._csa_checkpoint_evidence
                else:
                    model.load_state_dict(state, strict=True)
                if args.legacy_spconv_rsck:
                    for key, tensor in model.state_dict().items():
                        torch.testing.assert_close(tensor, state[key], rtol=0, atol=0)
                    report['loaded_tensors_exactly_match_converted_state'] = True
                with args.checkpoint.open('rb') as stream:
                    digest = hashlib.sha256()
                    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                        digest.update(chunk)
                report.update(checkpoint_sha256=digest.hexdigest(), model_loaded_strictly=True,
                              model_inference_tested=False)
                if args.synthetic_forward:
                    free_bytes, _ = torch.cuda.mem_get_info()
                    if free_bytes < 6 * 1024 ** 3:
                        raise RuntimeError('Less than 6 GiB free VRAM; refusing full-size synthetic probe')
                    model = model.cuda().eval()
                    torch.cuda.reset_peak_memory_stats()
                    torch.manual_seed(321)
                    camera_count = cfg.model.num_cams
                    sweeps = cfg.model.img_encoder.queue_len
                    height, width = cfg.model.img_encoder.final_dim
                    intrinsic = torch.tensor([[250., 0., width / 2], [0., 250., height / 2], [0., 0., 1.]])
                    meta = {'cam_intrinsic': intrinsic.repeat(camera_count, 1, 1),
                            'ida_mats': torch.eye(4).repeat(camera_count, 1, 1),
                            'currlidar2keycam': torch.eye(4).repeat(camera_count, 1, 1),
                            'lidar2img': torch.eye(4).repeat(camera_count, 1, 1)}
                    # Deliberately synthetic geometry, never labelled as sensor
                    # calibration or evidence of prediction/driving quality.
                    points = torch.rand(10000, 5, device='cuda')
                    points[:, :3] = points[:, :3] * torch.tensor([36., 36., 6.], device='cuda') + torch.tensor([-7., -18., -3.], device='cuda')
                    batch = {'img': torch.zeros(1, sweeps, camera_count, 3, height, width, device='cuda'),
                             'img_metas': [[meta for _ in range(sweeps)]],
                             'points': points[None, None].repeat(1, sweeps, 1, 1),
                             'target_point': torch.tensor([[10., 0.]], device='cuda'),
                             'target_command': torch.tensor([[0., 0., 0., 1., 0., 0.]], device='cuda'),
                             'target_command_raw': torch.tensor([3], device='cuda'),
                             'speed': torch.tensor([0.], device='cuda')}
                    started = time.monotonic()
                    with torch.no_grad():
                        if args.driveadapter_root:
                            from mmcv.parallel import DataContainer
                            # Original union2one supplies six previous-control /
                            # velocity values in a CPU-only collated container.
                            batch['state_list'] = DataContainer([[torch.zeros(6)]], cpu_only=True)
                            route_mask = torch.zeros(1, 192, 192, device='cuda')
                            route_mask[:, 32:160, 88:104] = 1
                            prediction = model.forward_inference(batch, route_mask)
                        else:
                            prediction = model.forward_inference(batch)
                    torch.cuda.synchronize()
                    tensors = {k: v for k, v in prediction.items() if torch.is_tensor(v)}
                    if not tensors or not all(torch.isfinite(v).all().item() for v in tensors.values()):
                        raise RuntimeError('Synthetic forward has no tensor outputs or non-finite outputs')
                    report['synthetic_forward'] = {'ok': True, 'input_is_synthetic': True,
                        'image_shape': list(batch['img'].shape), 'point_count': len(points),
                        'output_shapes': {k: list(v.shape) for k, v in tensors.items()},
                        'seconds': time.monotonic() - started,
                        'peak_allocated_bytes': torch.cuda.max_memory_allocated(),
                        'driving_quality_verified': False}
                    report['model_inference_tested'] = True
        if args.gpu_probe:
            if not args.sparse_only:
                from mmcv.ops.multi_scale_deform_attn import (
                    MultiScaleDeformableAttnFunction, multi_scale_deformable_attn_pytorch)
                torch.manual_seed(123)
                shape = torch.tensor([[2, 2], [1, 1]], dtype=torch.long, device='cuda')
                starts = torch.tensor([0, 4], dtype=torch.long, device='cuda')
                values = torch.randn(1, 5, 2, 4, device='cuda', requires_grad=True)
                locations = torch.rand(1, 3, 2, 2, 2, 2, device='cuda', requires_grad=True)
                weights = torch.rand(1, 3, 2, 2, 2, device='cuda', requires_grad=True)
                actual = MultiScaleDeformableAttnFunction.apply(values, shape, starts, locations, weights, 1)
                references = [x.detach().cpu().requires_grad_() for x in (values, locations, weights)]
                expected = multi_scale_deformable_attn_pytorch(references[0], shape.cpu(), references[1], references[2])
                torch.testing.assert_close(actual.cpu(), expected, rtol=1e-4, atol=1e-5)
                actual.sum().backward()
                expected.sum().backward()
                for actual_input, reference in zip((values, locations, weights), references):
                    torch.testing.assert_close(actual_input.grad.cpu(), reference.grad, rtol=1e-4, atol=1e-5)
                report['deformable_attention_check'] = {'dtype': 'float32', 'cpu_reference': True,
                                                        'forward': True, 'backward': True}
                empty_values = values.detach().clone().requires_grad_()
                empty_locations = torch.empty(1, 0, 2, 2, 2, 2, device='cuda', requires_grad=True)
                empty_weights = torch.empty(1, 0, 2, 2, 2, device='cuda', requires_grad=True)
                empty_output = MultiScaleDeformableAttnFunction.apply(
                    empty_values, shape, starts, empty_locations, empty_weights, 1)
                if tuple(empty_output.shape) != (1, 0, 8):
                    raise RuntimeError('Empty-query attention returned an incorrect shape')
                empty_output.sum().backward()
                torch.cuda.synchronize()
                torch.testing.assert_close(empty_values.grad, torch.zeros_like(empty_values))
                if empty_locations.grad.numel() or empty_weights.grad.numel():
                    raise RuntimeError('Empty-query gradients are not empty')
                report['deformable_attention_check']['empty_query_forward_backward'] = True
            import spconv.pytorch as spconv
            if args.legacy_spconv_rsck:
                from legacy_sparse_weights import convert_rsck_state
                conv = spconv.SparseConv3d(32, 32, 3, bias=False).cuda()
                legacy = torch.arange(3*3*3*32*32, dtype=torch.float32, device='cuda').reshape(3,3,3,32,32)/32768
                converted, _ = convert_rsck_state(conv, {'weight': legacy})
                conv.load_state_dict(converted, strict=True)
                coordinates = torch.cartesian_prod(torch.arange(3), torch.arange(3), torch.arange(3)).to('cuda', dtype=torch.int32)
                indices = torch.cat([torch.zeros(27,1,device='cuda',dtype=torch.int32), coordinates], dim=1)
                features = torch.arange(27*32,device='cuda',dtype=torch.float32).reshape(27,32)/1024
                sparse = spconv.SparseConvTensor(features, indices, [3,3,3], 1)
                actual = conv(sparse)
                dense = features.reshape(3,3,3,32).permute(3,0,1,2).unsqueeze(0)
                # Independent float64 CPU reference: CUDA dense convolution may
                # select TF32, which cannot establish float32 layout accuracy.
                reference = torch.nn.functional.conv3d(dense.cpu().double(), legacy.permute(4,3,0,1,2).contiguous().cpu().double())
                assert actual.indices.tolist() == [[0,0,0,0]]
                torch.testing.assert_close(actual.features.cpu().double(), reference.flatten(1), rtol=1e-4, atol=1e-4)
                report['sparse_layout_numeric_check'] = {'cpu_layout_formula': 'RSCK[kd,kh,kw,in,out] -> torch OIDHW', 'gpu_forward_matches_dense': True, 'nonuniform_weights': True}
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
        report.update(error_type=type(exc).__name__, error=str(exc), traceback=traceback.format_exc())
    serialized = json.dumps(report, indent=2) + '\n'
    if args.report:
        with args.report.open('x', encoding='utf-8') as stream:
            stream.write(serialized)
            stream.flush()
            os.fsync(stream.fileno())
    print(serialized, end='')
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
