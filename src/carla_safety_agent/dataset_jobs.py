"""Coordinate dataset service starts inside one bridge process."""
from contextlib import ExitStack


def start_dataset_job(services, name, payload):
    if name not in services:raise ValueError('Unknown dataset service')
    # Workers only acquire their own service lock at completion. Fixed order
    # prevents concurrent HTTP starts from both observing an idle peer.
    with ExitStack() as stack:
        for key in sorted(services):stack.enter_context(services[key].lock)
        if any(service.active is not None for key,service in services.items() if key!=name):
            raise ValueError('Another dataset background task is running; retry explicitly later')
        return services[name].start(payload)
