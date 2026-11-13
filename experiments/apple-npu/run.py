#!/usr/bin/env python3
"""Create, compile and execute a CoreML ReLU model on the Apple Neural Engine.

This is a device-level experiment, not a NEX std/device provider. It requires
coremltools and Xcode's coremlcompiler. The report records the compute-plan
preferred device and the actual prediction.
"""
import argparse, json, subprocess, sys
from pathlib import Path
import numpy as np
import coremltools as ct
from coremltools.models import datatypes
from coremltools.models.compute_plan import MLComputePlan
from coremltools.models.neural_network import NeuralNetworkBuilder

p = argparse.ArgumentParser()
p.add_argument('--output', type=Path, required=True)
a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=True)
builder = NeuralNetworkBuilder(
    input_features=[('x', datatypes.Array(1, 4, 1))],
    output_features=[('y', datatypes.Array(1, 4, 1))])
builder.add_activation(name='relu', non_linearity='RELU', input_name='x', output_name='y')
package = a.output / 'relu.mlpackage'
ct.models.MLModel(builder.spec).save(str(package))
compiled = a.output / 'compiled'
subprocess.run(['xcrun', 'coremlcompiler', 'compile', str(package), str(compiled)], check=True)
plan = MLComputePlan.load_from_path(str(compiled / 'relu.mlmodelc'))
usage = plan.get_compute_device_usage_for_neuralnetwork_layer(
    plan.model_structure.neuralnetwork.layers[0])
model = ct.models.MLModel(str(package), compute_units=ct.ComputeUnit.CPU_AND_NE)
x = np.array([[[-1.0], [0.0], [2.0], [3.0]]], dtype=np.float32)
y = np.asarray(model.predict({'x': x})['y'])
report = {
    'schema': 'nex.apple-coreml-device/1',
    'ok': bool(np.array_equal(y, np.maximum(x, 0))),
    'model': 'relu', 'shape': list(x.shape),
    'compute_units': 'CPU_AND_NE',
    'preferred_compute_device': type(usage.preferred_compute_device).__name__ if usage else None,
    'supported_compute_devices': [type(d).__name__ for d in usage.supported_compute_devices] if usage else [],
    'input': x.reshape(-1).tolist(), 'output': y.reshape(-1).tolist(),
}
(a.output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
sys.exit(0 if report['ok'] else 1)
