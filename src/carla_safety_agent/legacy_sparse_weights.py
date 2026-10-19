"""Explicit RSCK -> KRSC conversion only for real spconv 3D weight modules."""
from copy import deepcopy
from collections import OrderedDict


def convert_rsck_state(model, state):
    from spconv.constants import SAVED_WEIGHT_LAYOUT
    from spconv.pytorch.conv import SparseConvolution
    if SAVED_WEIGHT_LAYOUT:
        raise ValueError('Disable implicit spconv saved-layout conversion; do not convert twice')
    converted = OrderedDict(state)
    converted._metadata = deepcopy(getattr(state, '_metadata', {}))
    records = []
    for name, module in model.named_modules():
        if not isinstance(module, SparseConvolution):
            continue
        if module.ndim != 3:
            raise ValueError('Only explicitly audited 3D sparse kernels are supported')
        key = (name + '.' if name else '') + 'weight'
        source = state[key]
        rsck = (*module.kernel_size, module.in_channels, module.out_channels)
        krsc = (module.out_channels, *module.kernel_size, module.in_channels)
        if tuple(source.shape) != rsck or tuple(module.weight.shape) != krsc:
            raise ValueError('Sparse weight does not match the declared RSCK contract: ' + key)
        converted[key] = source.permute(4, 0, 1, 2, 3).contiguous()
        # MMDet3D's actual SparseModule loader interprets metadata version=2
        # as already KRSC. Update only the converted module's format metadata,
        # or that loader would transpose the converted tensor a second time.
        converted._metadata[name] = {**converted._metadata.get(name, {}), 'version': 2}
        records.append({'key': key, 'source': list(rsck), 'target': list(krsc), 'permutation': [4, 0, 1, 2, 3], 'converted_module_metadata_version': 2})
    if not records:
        raise ValueError('No real 3D spconv modules were found')
    return converted, records
