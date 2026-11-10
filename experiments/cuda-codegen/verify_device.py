"""Compile pinned emitted CUDA with NVRTC and execute it on an actual CUDA GPU."""
import argparse
import ctypes as C
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

V, I, U, Z, D = C.c_void_p, C.c_int, C.c_uint, C.c_size_t, C.c_uint64


def bind(library, name, args):
    function = getattr(library, name)
    function.argtypes, function.restype = args, I
    return function


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--matrix', required=True, type=Path)
    parser.add_argument('--nvrtc', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--index', type=int, default=0)
    args = parser.parse_args()
    out = args.output.absolute()
    out.mkdir(exist_ok=False)
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    report = {'schema': 'nex.experimental-CUDA-physical/1', 'ok': False,
              'experimental': True, 'NEX_owned_provider_integrated': False,
              'CPU_fallback': False, 'cases': [], 'allocations': 0, 'frees': 0,
              'kernel_launches': 0, 'physical_completions': 0, 'cleanup_errors': [],
              'matrix_sha256': sha(args.matrix), 'NVRTC_sha256': sha(args.nvrtc)}
    started = time.monotonic()
    context, stream, libraries = V(), V(), []
    driver = None

    def save():
        report['seconds'] = time.monotonic() - started
        pending = out / 'report.tmp'
        pending.write_text(json.dumps(report, indent=2) + '\n')
        # Windows observers may briefly hold the old report without delete sharing.
        for attempt in range(50):
            try:
                pending.replace(out / 'report.json')
                return
            except OSError as error:
                if os.name != 'nt' or error.winerror not in (5, 32) or attempt == 49:
                    raise
                time.sleep(0.1)

    def checked(function, *values):
        code = function(*values)
        if code:
            raise RuntimeError(function.__name__ + ' returned ' + str(code))

    try:
        save()
        matrix = json.loads(args.matrix.read_bytes())
        assert matrix['ok'] and matrix['GPU_execution_claimed'] is False
        assert 1 <= len(matrix['cases']) <= 1024
        if os.name == 'nt':
            libraries.append(os.add_dll_directory(str(args.nvrtc.resolve().parent)))
            rtc = C.CDLL(str(args.nvrtc.resolve()), winmode=0x1100)
            driver_path = Path(os.environ['SystemRoot']) / 'System32/nvcuda.dll'
            driver = C.WinDLL(str(driver_path), winmode=0x800)
            report['CUDA_driver_sha256'] = sha(driver_path)
        else:
            rtc = C.CDLL(str(args.nvrtc.resolve()))
            driver = C.CDLL('libcuda.so.1')
        version = bind(rtc, 'nvrtcVersion', [C.POINTER(I), C.POINTER(I)])
        major, minor = I(), I()
        checked(version, C.byref(major), C.byref(minor))
        assert major.value >= 12, 'NVRTC12+ is required for CUDA C++20'
        report['NVRTC_version'] = [major.value, minor.value]
        create = bind(rtc, 'nvrtcCreateProgram', [C.POINTER(V), C.c_char_p, C.c_char_p, I, V, V])
        compile_program = bind(rtc, 'nvrtcCompileProgram', [V, I, C.POINTER(C.c_char_p)])
        get_log_size = bind(rtc, 'nvrtcGetProgramLogSize', [V, C.POINTER(Z)])
        get_log = bind(rtc, 'nvrtcGetProgramLog', [V, V])
        get_ptx_size = bind(rtc, 'nvrtcGetPTXSize', [V, C.POINTER(Z)])
        get_ptx = bind(rtc, 'nvrtcGetPTX', [V, V])
        destroy_program = bind(rtc, 'nvrtcDestroyProgram', [C.POINTER(V)])
        init = bind(driver, 'cuInit', [U])
        get_count = bind(driver, 'cuDeviceGetCount', [C.POINTER(I)])
        get_device = bind(driver, 'cuDeviceGet', [C.POINTER(I), I])
        get_name = bind(driver, 'cuDeviceGetName', [V, I, I])
        get_attribute = bind(driver, 'cuDeviceGetAttribute', [C.POINTER(I), I, I])
        get_pci = bind(driver, 'cuDeviceGetPCIBusId', [V, I, I])
        create_context = bind(driver, 'cuCtxCreate_v2', [C.POINTER(V), U, I])
        destroy_context = bind(driver, 'cuCtxDestroy_v2', [V])
        load_module = bind(driver, 'cuModuleLoadData', [C.POINTER(V), V])
        unload_module = bind(driver, 'cuModuleUnload', [V])
        get_function = bind(driver, 'cuModuleGetFunction', [C.POINTER(V), V, C.c_char_p])
        allocate = bind(driver, 'cuMemAlloc_v2', [C.POINTER(D), Z])
        free = bind(driver, 'cuMemFree_v2', [D])
        upload = bind(driver, 'cuMemcpyHtoD_v2', [D, V, Z])
        download = bind(driver, 'cuMemcpyDtoH_v2', [V, D, Z])
        create_stream = bind(driver, 'cuStreamCreate', [C.POINTER(V), U])
        sync_stream = bind(driver, 'cuStreamSynchronize', [V])
        destroy_stream = bind(driver, 'cuStreamDestroy_v2', [V])
        create_event = bind(driver, 'cuEventCreate', [C.POINTER(V), U])
        record_event = bind(driver, 'cuEventRecord', [V, V])
        sync_event = bind(driver, 'cuEventSynchronize', [V])
        query_event = bind(driver, 'cuEventQuery', [V])
        elapsed = bind(driver, 'cuEventElapsedTime', [C.POINTER(C.c_float), V, V])
        destroy_event = bind(driver, 'cuEventDestroy_v2', [V])
        launch = bind(driver, 'cuLaunchKernel', [V, U, U, U, U, U, U, U, V, V, V])
        checked(init, 0)
        count, device = I(), I()
        checked(get_count, C.byref(count))
        assert 0 <= args.index < count.value
        checked(get_device, C.byref(device), args.index)
        name, pci = C.create_string_buffer(256), C.create_string_buffer(64)
        checked(get_name, name, len(name), device)
        checked(get_pci, pci, len(pci), device)
        checked(get_attribute, C.byref(major), 75, device)
        checked(get_attribute, C.byref(minor), 76, device)
        options = [b'--std=c++20', ('--gpu-architecture=compute_%d%d' % (major.value, minor.value)).encode(), b'--generate-line-info']
        report['device'] = {'index': args.index, 'name': name.value.decode(),
                            'PCI_bus': pci.value.decode(), 'compute_capability': [major.value, minor.value]}
        report['NVRTC_options'] = [x.decode() for x in options]
        checked(create_context, C.byref(context), 0, device)
        checked(create_stream, C.byref(stream), 1)
        for index, case in enumerate(matrix['cases']):
            shader = (args.matrix.resolve().parent / case['shader']).resolve()
            assert shader.is_relative_to(args.matrix.resolve().parent)
            assert shader.is_file() and shader.stat().st_size <= 16 * 1024**2
            assert sha(shader) == case['shader_sha256']
            assert 1 <= len(case['lanes']) <= 32768 and 1 <= case['steps'] <= 65536
            arity = len(case['metadata']['parameter_types'])
            assert arity <= 8 and all(len(row['arguments']) == arity for row in case['lanes'])
            program = V()
            checked(create, C.byref(program), shader.read_bytes(), shader.name.encode(), 0, None, None)
            try:
                code = compile_program(program, len(options), (C.c_char_p * len(options))(*options))
                size = Z()
                checked(get_log_size, program, C.byref(size))
                assert size.value <= 16 * 1024**2
                log = C.create_string_buffer(size.value)
                checked(get_log, program, log)
                (out / ('compile-' + str(index) + '.log')).write_bytes(log.value)
                assert code == 0, (case['name'], case['layout'], code, log.value.decode(errors='replace'))
                checked(get_ptx_size, program, C.byref(size))
                assert size.value <= 64 * 1024**2
                ptx = C.create_string_buffer(size.value)
                checked(get_ptx, program, ptx)
                (out / ('kernel-' + str(index) + '.ptx')).write_bytes(ptx.raw)
            finally:
                checked(destroy_program, C.byref(program))
            module, function, begin, done = V(), V(), V(), V()
            allocations, inputs = [], []
            settled = True
            try:
                checked(load_module, C.byref(module), ptx)
                checked(get_function, C.byref(function), module, b'nex_generated_cuda_map')
                n = len(case['lanes'])
                rows = [[int(x) for x in row['arguments']] for row in case['lanes']]
                columns = [[x for row in rows for x in row]] if case['layout'] == 'rows' else [[rows[lane][p] for lane in range(n)] for p in range(arity)]

                def buffer(array):
                    pointer = D()
                    checked(allocate, C.byref(pointer), C.sizeof(array))
                    report['allocations'] += 1
                    allocations.append(pointer)
                    checked(upload, pointer, array, C.sizeof(array))
                    return pointer

                pointers = []
                for column in columns:
                    array = (C.c_longlong * max(1, len(column)))(*column)
                    pointer = buffer(array)
                    pointers.append(pointer)
                    inputs.append((array, pointer, bytes(array)))
                actual = (C.c_longlong * (n + 3))(*([123456789] * (n + 3)))
                errors = (U * (n + 3))(*([98765] * (n + 3)))
                output_pointer, error_pointer = buffer(actual), buffer(errors)
                parameters = [*pointers, output_pointer, error_pointer, U(n), U(case['steps'])]
                arguments = (V * len(parameters))(*[C.cast(C.byref(x), V) for x in parameters])
                checked(create_event, C.byref(begin), 0)
                checked(create_event, C.byref(done), 0)
                checked(record_event, begin, stream)
                settled = False
                checked(launch, function, (n + 127) // 128 + 1, 1, 1, 128, 1, 1, 0, stream, arguments, None)
                report['kernel_launches'] += 1
                checked(record_event, done, stream)
                checked(sync_event, done)
                checked(query_event, done)
                checked(sync_stream, stream)
                settled = True
                report['physical_completions'] += 1
                milliseconds = C.c_float()
                checked(elapsed, C.byref(milliseconds), begin, done)
                assert math.isfinite(milliseconds.value) and milliseconds.value >= 0
                checked(download, actual, output_pointer, C.sizeof(actual))
                checked(download, errors, error_pointer, C.sizeof(errors))
                assert list(actual) == [int(x['value']) for x in case['lanes']] + [123456789] * 3
                assert list(errors) == [x['error'] for x in case['lanes']] + [98765] * 3
                for array, pointer, original in inputs:
                    checked(download, array, pointer, C.sizeof(array))
                    assert bytes(array) == original
                report['cases'].append({'name': case['name'], 'layout': case['layout'],
                    'shader_sha256': case['shader_sha256'], 'PTX_sha256': sha(out / ('kernel-' + str(index) + '.ptx')),
                    'lanes': n, 'physical_GPU_event_ms': milliseconds.value,
                    'completion_event_and_stream_verified': True,
                    'inputs_unchanged': True, 'excess_lanes_untouched': True,
                    'lane_values_and_errors_match': True})
            finally:
                if not settled:
                    checked(sync_stream, stream)
                    settled = True
                if settled:
                    for event in [begin, done]:
                        if event.value:
                            checked(destroy_event, event)
                    for pointer in reversed(allocations):
                        checked(free, pointer)
                        report['frees'] += 1
                    if module.value:
                        checked(unload_module, module)
            save()
        assert report['allocations'] == report['frees']
        assert len(report['cases']) == report['kernel_launches'] == report['physical_completions'] == len(matrix['cases'])
        report.update(ok=True, actual_GPU_execution=True, state='passed',
                      generated_kernel_cases=len(report['cases']),
                      lane_results_checked=sum(x['lanes'] for x in report['cases']))
    except BaseException as error:
        report.update(ok=False, state='failed', error=repr(error), traceback=traceback.format_exc())
    finally:
        if driver is not None:
            for value, function_name in [(stream, 'cuStreamDestroy_v2'), (context, 'cuCtxDestroy_v2')]:
                if value.value:
                    try:
                        checked(bind(driver, function_name, [V]), value)
                    except BaseException as error:
                        report['cleanup_errors'].append(repr(error))
                        report.update(ok=False, state='failed')
        for directory in libraries:
            directory.close()
        save()
    print(json.dumps({k: report.get(k) for k in ['ok', 'state', 'device', 'generated_kernel_cases', 'lane_results_checked', 'error']}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    sys.exit(main())
