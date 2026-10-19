"""Safe full-coverage checkpoint loading for original model adapters."""
from collections.abc import Mapping
import hashlib


def load_complete_checkpoint(model, filename, map_location='cpu', strict=True,
                             legacy_sparse_rsck=False, **kwargs):
    import torch
    if map_location != 'cpu' or strict is not True or kwargs:
        raise ValueError('Only strict CPU checkpoint deserialization is supported')
    # Hash and deserialize the same open file, not two independently resolved
    # paths. Never fall back to unrestricted legacy pickle loading.
    with open(filename, 'rb') as stream:
        hasher = hashlib.sha256()
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            hasher.update(chunk)
        digest = hasher.hexdigest()
        stream.seek(0)
        checkpoint = torch.load(stream, map_location='cpu', weights_only=True)
    if not isinstance(checkpoint, Mapping) or not isinstance(checkpoint.get('state_dict'), Mapping):
        raise ValueError('Checkpoint must contain a complete state_dict')
    state = checkpoint['state_dict']
    conversion = None
    if legacy_sparse_rsck:
        from .legacy_sparse_weights import convert_rsck_state
        state, conversion = convert_rsck_state(model, state)
    expected = model.state_dict()
    if set(state) != set(expected):
        raise ValueError('Checkpoint parameter keys do not completely match the model')
    for key, value in state.items():
        if not torch.is_tensor(value) or value.shape != expected[key].shape:
            raise ValueError(f'Checkpoint tensor shape mismatch: {key}')
        if value.dtype != expected[key].dtype:
            raise ValueError(f'Checkpoint tensor dtype mismatch: {key}')
        if (value.is_floating_point() or value.is_complex()) and not torch.isfinite(value).all().item():
            raise ValueError(f'Non-finite checkpoint tensor: {key}')
    model.load_state_dict(state, strict=True)
    for key, value in model.state_dict().items():
        torch.testing.assert_close(value, state[key], rtol=0, atol=0)
    model._csa_checkpoint_evidence = {'sha256': digest, 'entries': len(state),
                                     'strict': True, 'weights_only': True}
    if conversion is not None:
        model._csa_checkpoint_evidence['sparse_weight_conversion'] = conversion
    return checkpoint
