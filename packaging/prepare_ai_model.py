"""Build-time conversion of the pinned BSD Real-ESRGAN weights to ONNX.

No PyTorch installation or arbitrary pickle globals are needed. The application
never imports this file. Normal Windows builds only verify bundled assets.
"""
import argparse
from collections import OrderedDict
import hashlib
from io import BytesIO
import json
from pathlib import Path
import pickle
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'models'
WEIGHTS_SHA256 = '8dc7edb9ac80ccdc30c3a5dca6616509367f05fbc184ad95b731f05bece96292'
LICENSE_SHA256 = '4a699ec4863d96a91fc265948a0c90033f7e8735d515524dcf3444736406e0c2'
URL = 'https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth'


def digest(path):
    data = path.read_bytes()
    # Git on Windows can check text out with CRLF. Only the license's line
    # endings are normalised; all content and every model byte stay checked.
    if path.name == 'Real-ESRGAN-LICENSE.txt':
        data = data.replace(b'\r\n', b'\n')
    return hashlib.sha256(data).hexdigest()


def verify():
    records = json.loads((MODEL / 'manifest.json').read_text(encoding='utf-8'))
    for filename, expected in records['sha256'].items():
        if digest(MODEL / filename) != expected:
            raise ValueError('AI asset checksum mismatch: ' + filename)
    if digest(MODEL / 'source/realesr-general-x4v3.pth') != WEIGHTS_SHA256:
        raise ValueError('Original AI weights checksum mismatch')
    if digest(MODEL / 'Real-ESRGAN-LICENSE.txt') != LICENSE_SHA256:
        raise ValueError('AI license checksum mismatch')
    print('Bundled offline AI model verified.')


def convert():
    import numpy as np
    import onnx
    from onnx import helper as h, numpy_helper as nh, TensorProto as T
    source = MODEL / 'source/realesr-general-x4v3.pth'
    if digest(source) != WEIGHTS_SHA256:
        raise ValueError('Unexpected model weights')
    with zipfile.ZipFile(source) as archive:
        def rebuild(storage, offset, size, stride, *_):
            data = np.frombuffer(storage, dtype='<f4')
            arr = np.ndarray(tuple(size), dtype='<f4', buffer=data,
                             offset=offset * 4, strides=tuple(v * 4 for v in stride))
            return arr.copy()

        class Reader(pickle.Unpickler):
            def find_class(self, module, name):
                allowed = {('collections', 'OrderedDict'): OrderedDict,
                           ('torch._utils', '_rebuild_tensor_v2'): rebuild,
                           ('torch', 'FloatStorage'): 'FloatStorage'}
                if (module, name) not in allowed:
                    raise ValueError('Unexpected checkpoint global')
                return allowed[module, name]

            def persistent_load(self, value):
                tag, dtype, key, device, count = value
                if tag != 'storage' or dtype != 'FloatStorage' or not str(key).isdigit():
                    raise ValueError('Unexpected model storage')
                data = archive.read('archive/data/' + key)
                if len(data) != count * 4:
                    raise ValueError('Unexpected tensor size')
                return data

        weights = Reader(BytesIO(archive.read('archive/data.pkl'))).load()['params']
    nodes, initializers = [], []
    current = 'input'
    indices = sorted({int(k.split('.')[1]) for k in weights})
    for index in indices:
        key = f'body.{index}'
        w = weights[key + '.weight']
        output = f'layer_{index}'
        if w.ndim == 4:
            for suffix in ('weight', 'bias'):
                initializers.append(nh.from_array(weights[key + '.' + suffix], key + '.' + suffix))
            nodes.append(h.make_node('Conv', [current, key + '.weight', key + '.bias'],
                                     [output], pads=[1, 1, 1, 1], strides=[1, 1]))
        else:
            name = key + '.weight'
            initializers.append(nh.from_array(w.reshape(-1, 1, 1), name))
            nodes.append(h.make_node('PRelu', [current, name], [output]))
        current = output
    nodes.append(h.make_node('DepthToSpace', [current], ['detail'], blocksize=4, mode='CRD'))
    initializers.append(nh.from_array(np.array([1, 1, 4, 4], np.float32), 'scales'))
    nodes.append(h.make_node('Resize', ['input', '', 'scales'], ['base'],
                             mode='nearest', coordinate_transformation_mode='asymmetric', nearest_mode='floor'))
    nodes.append(h.make_node('Add', ['detail', 'base'], ['output']))
    graph = h.make_graph(nodes, 'RealESRGAN_SRVGG_compact',
                         [h.make_tensor_value_info('input', T.FLOAT, [1, 3, 'h', 'w'])],
                         [h.make_tensor_value_info('output', T.FLOAT, [1, 3, 'oh', 'ow'])], initializers)
    model = h.make_model(graph, opset_imports=[h.make_opsetid('', 17)], producer_name='OfflinePDF')
    model.ir_version = 9
    onnx.checker.check_model(model)
    target = MODEL / 'realesr-general-x4v3.onnx'
    onnx.save(model, target)
    record = {'model': 'realesr-general-x4v3', 'source_url': URL,
              'license': 'BSD-3-Clause', 'scale': 4,
              'sha256': {str(p.relative_to(MODEL)).replace('\\', '/'): digest(p)
                         for p in [target, source, MODEL / 'Real-ESRGAN-LICENSE.txt']}}
    (MODEL / 'manifest.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    verify()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--convert', action='store_true')
    args = parser.parse_args()
    if args.convert:
        convert()
    else:
        verify()
