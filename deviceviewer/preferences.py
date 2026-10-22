"""Settings and ordering shared by the window, notifications and tray."""
THRESHOLDS = (10, 20, 30, 40, 50)


def normalize_config(saved):
    config = {'interval': 30, 'alerts': True, 'threshold': 50,
              'device_order': [], 'tray_device': None}
    if isinstance(saved, dict):
        config.update(saved)
    config.pop('topmost', None)
    try:
        config['interval'] = max(10, min(300, int(config['interval'])))
    except (TypeError, ValueError):
        config['interval'] = 30
    if config['threshold'] not in THRESHOLDS:
        config['threshold'] = 50
    if not isinstance(config['device_order'], list):
        config['device_order'] = []
    config['device_order'] = list(dict.fromkeys(k for k in config['device_order'] if isinstance(k, str)))
    if not isinstance(config['tray_device'], str):
        config['tray_device'] = None
    return config


def ordered_devices(states, order):
    positions = {key: i for i, key in enumerate(order)}
    return sorted(states, key=lambda s: (positions.get(s.key, len(order)), s.brand, s.name, s.key))


def selected_device(states, key):
    return next((s for s in states if s.key == key), states[0] if states else None)


def is_low(state, threshold):
    return state.percent is not None and state.percent < threshold and not state.charging
