"""3D model loader for guga desktop pet."""

import struct
from pathlib import Path
from typing import Any

import numpy as np

try:
    from pygltflib import GLTF2
    HAS_GLTF = True
except ImportError:
    HAS_GLTF = False


class ModelData:
    def __init__(self):
        self.vao = None
        self.vertex_count = 0

    def upload(self, ctx):
        pass

    def render(self):
        if self.vao:
            self.vao.render()


SHADER_VS = """#version 330
in vec3 in_pos;
in vec3 in_color;
out vec3 v_color;
uniform mat4 model;
uniform mat4 view;
uniform mat4 proj;
void main() {
    gl_Position = proj * view * model * vec4(in_pos, 1.0);
    v_color = in_color;
}"""

SHADER_FS = """#version 330
in vec3 v_color;
out vec4 f_color;
void main() {
    f_color = vec4(v_color, 1.0);
}"""


class CubeModel(ModelData):
    def __init__(self):
        super().__init__()
        v = 0.5
        verts = np.array([
            -v,-v, v, -v,-v, v,  v,-v, v,  v,-v, v,  v, v, v,  v, v, v, -v, v, v, -v, v, v,
             v,-v,-v,  v,-v,-v, -v,-v,-v, -v,-v,-v, -v, v,-v, -v, v,-v,  v, v,-v,  v, v,-v,
            -v, v, v, -v, v, v,  v, v, v,  v, v, v,  v, v,-v,  v, v,-v, -v, v,-v, -v, v,-v,
            -v,-v,-v, -v,-v,-v,  v,-v,-v,  v,-v,-v,  v,-v, v,  v,-v, v, -v,-v, v, -v,-v, v,
             v,-v, v,  v,-v, v,  v,-v,-v,  v,-v,-v,  v, v,-v,  v, v,-v,  v, v, v,  v, v, v,
            -v,-v,-v, -v,-v,-v, -v,-v, v, -v,-v, v, -v, v, v, -v, v, v, -v, v,-v, -v, v,-v,
        ], dtype=np.float32)
        colors = np.array([
            0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,
            0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,
            0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,0.2,0.2,0.8,
            0.8,0.8,0.2,0.8,0.8,0.2,0.8,0.8,0.2,0.8,0.8,0.2,0.8,0.8,0.2,0.8,0.8,0.2,0.8,0.8,0.2,0.8,0.8,0.2,
            0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,
            0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,0.5,0.2,0.8,
        ], dtype=np.float32)
        self.gpu_data = np.hstack([verts.reshape(-1,3), colors.reshape(-1,3)]).flatten()
        self.vertex_count = 36

    def upload(self, ctx):
        prog = ctx.program(vertex_shader=SHADER_VS, fragment_shader=SHADER_FS)
        vbo = ctx.buffer(self.gpu_data.tobytes())
        self.vao = ctx.simple_vertex_array(prog, vbo, 'in_pos', 'in_color')


class TriangleModel(ModelData):
    def __init__(self):
        super().__init__()
        self.data = np.array([
             0.0, 0.6,0.0, 1.0,0.3,0.3,
            -0.5,-0.4,0.0, 0.3,1.0,0.3,
             0.5,-0.4,0.0, 0.3,0.3,1.0,
        ], dtype=np.float32)
        self.vertex_count = 3

    def upload(self, ctx):
        prog = ctx.program(vertex_shader=SHADER_VS, fragment_shader=SHADER_FS)
        vbo = ctx.buffer(self.data.tobytes())
        self.vao = ctx.simple_vertex_array(prog, vbo, 'in_pos', 'in_color')


class GLTFLoader:
    @staticmethod
    def load(path, ctx):
        path = Path(path)
        if not path.exists():
            print("[loader] not found, using cube")
            return CubeModel()
        if not HAS_GLTF:
            print("[loader] pygltflib missing, using cube")
            return CubeModel()
        try:
            gltf = GLTF2().load(str(path))
            return GLTFLoader._parse(gltf, path, ctx)
        except Exception as e:
            print("[loader] error:", e, ", using cube")
            return CubeModel()

    @staticmethod
    def _parse(gltf, base_path, ctx):
        model = ModelData()
        bin_data = None
        if gltf.buffers and gltf.buffers[0].uri:
            bp = base_path.parent / gltf.buffers[0].uri
            if bp.exists():
                bin_data = bp.read_bytes()

        all_data = []
        for mesh in gltf.meshes:
            for prim in mesh.primitives:
                pos_acc = gltf.accessors[prim.attributes.POSITION]
                pv = gltf.bufferViews[pos_acc.bufferView]
                if bin_data:
                    off = pv.byteOffset or 0
                    verts = np.frombuffer(bin_data, np.float32, pos_acc.count*3, off)
                    col = np.tile([0.6,0.7,0.9], pos_acc.count)
                    mesh_data = np.hstack([verts.reshape(-1,3), col.reshape(-1,3)]).flatten()
                    all_data.append(mesh_data)

        if all_data:
            buf = np.hstack(all_data).astype(np.float32)
            model.vertex_count = len(buf) // 6
            prog = ctx.program(vertex_shader=SHADER_VS, fragment_shader=SHADER_FS)
            vbo = ctx.buffer(buf.tobytes())
            model.vao = ctx.simple_vertex_array(prog, vbo, 'in_pos', 'in_color')
            print("[loader] loaded", model.vertex_count, "verts")
        else:
            return CubeModel()
        return model