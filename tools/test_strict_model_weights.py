"""Run in the isolated Torch environment; no CUDA or CARLA required."""
from pathlib import Path
import tempfile
import torch
from carla_safety_agent.strict_model_weights import load_complete_checkpoint


def main():
    with tempfile.TemporaryDirectory(prefix='strict-weights-') as directory:
        path = Path(directory) / 'weights.pth'
        model = torch.nn.Linear(3, 2)
        original = {key: value.clone() for key, value in model.state_dict().items()}
        torch.save({'state_dict': original}, path)
        load_complete_checkpoint(model, path)
        assert model._csa_checkpoint_evidence['entries'] == 2
        for case in ('missing', 'extra', 'shape', 'dtype', 'nan'):
            state = {key: value.clone() for key, value in original.items()}
            if case == 'missing': del state['bias']
            if case == 'extra': state['extra'] = torch.zeros(1)
            if case == 'shape': state['bias'] = torch.zeros(3)
            if case == 'dtype': state['bias'] = state['bias'].double()
            if case == 'nan': state['bias'][0] = float('nan')
            torch.save({'state_dict': state}, path)
            try:
                load_complete_checkpoint(model, path)
            except ValueError:
                pass
            else:
                raise AssertionError(f'Accepted invalid checkpoint: {case}')
            for key, value in model.state_dict().items():
                torch.testing.assert_close(value, original[key], rtol=0, atol=0)
        print('PASS: strict loading and five invalid checkpoints rejected before mutation')


if __name__ == '__main__':
    main()
