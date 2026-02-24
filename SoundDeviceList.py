import sounddevice as sd

def show_device(idx, device):
    print(f"  Device {idx}:")
    print(f"    Name: {device['name']}")
    print(f"    Host API: {device['hostapi']}")
    print(f"    Max Input Channels: {device['max_input_channels']}")
    print(f"    Default Sample Rate: {device['default_samplerate']}")
    print()

devices = sd.query_devices()
input_devices = []
output_devices = []

for idx, device in enumerate(devices):
    if device['max_input_channels'] > 0:
        input_devices.append((idx, device))
    if device['max_output_channels'] > 0:
        output_devices.append((idx, device))

print("Input Devices:")
for idx, device in input_devices:
    show_device(idx=idx, device=device)

print("\nOutput Devices:")
for idx, device in output_devices:
    show_device(idx=idx, device=device)

print("\nDefault Input Device:")
default_idev_idx = sd.default.device[0]
if default_idev_idx >= 0:
    show_device(default_idev_idx, devices[default_idev_idx])
else:
    print('  None.')

print("\nDefault Output Device:")
default_odev_idx = sd.default.device[1]
if default_odev_idx >= 0:
    show_device(default_odev_idx, devices[default_odev_idx])
else:
    print('  None.')
