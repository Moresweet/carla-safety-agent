"""Validate coverage across array and structured pre-model input archives."""
import math


def validate_input_coverage(required, array_names, structured):
    if not isinstance(required, list) or not required or not all(isinstance(n, str) for n in required) or len(required) != len(set(required)):
        raise ValueError('Invalid actual model input declaration')
    if not isinstance(structured, dict) or any(not isinstance(k, str) for k in structured):
        raise ValueError('Invalid structured input archive')
    arrays = set(array_names)
    if arrays & set(structured):
        raise ValueError('Input appears in both array and structured archives')
    if set(required) != arrays | set(structured):
        raise ValueError('Model input archive coverage mismatch')
    def finite_tree(value):
        if isinstance(value, dict):
            return bool(value) and all(isinstance(k, str) and finite_tree(v) for k, v in value.items())
        if isinstance(value, list):
            return all(finite_tree(v) for v in value)
        if isinstance(value, (str, bool, int)):
            return True
        return isinstance(value, float) and math.isfinite(value)
    if any(not isinstance(v, dict) or not finite_tree(v) for v in structured.values()):
        raise ValueError('Invalid or lossy structured model input')
