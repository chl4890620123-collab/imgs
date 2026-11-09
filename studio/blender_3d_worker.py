"""Run ONLY inside Blender: native .blend scene creation and checkpointed frames.

Example:
blender -b --factory-startup --python studio/blender_3d_worker.py -- \
  --mode build --project-root . --recipe media/3d/SHOT/scene.json \
  --blend media/3d/SHOT/scene.blend --frames-dir media/3d/SHOT/frames \
  --preview media/3d/SHOT/preview.png
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def vector3(value, default=(0.0, 0.0, 0.0)):
    return tuple(float(v) for v in (value if value is not None else default))


def rotation(value):
    return tuple(math.radians(float(v)) for v in (value or [0, 0, 0]))


def look_at(obj, target):
    direction = Vector(vector3(target)) - obj.location
    if direction.length > 1e-6:
        obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def create_material(data, name):
    color = str(data.get("color", "#9a9a9a")).lstrip("#")
    if len(color) != 6:
        raise ValueError("Material colors must be six-digit hex")
    channels = [int(color[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    material = bpy.data.materials.new(name=f"{name} material")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = (*channels, 1.0)
        principled.inputs["Metallic"].default_value = float(data.get("metallic", 0.0))
        principled.inputs["Roughness"].default_value = float(data.get("roughness", 0.55))
    material.diffuse_color = (*channels, 1.0)
    return material


def import_model(source):
    ext = source.suffix.lower()
    before = set(bpy.context.scene.objects)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(source))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(source))
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(source))
    else:
        raise ValueError(f"Unsupported model extension: {ext}")
    return [obj for obj in bpy.context.scene.objects if obj not in before]


def primitive(kind):
    if kind == "cube":
        bpy.ops.mesh.primitive_cube_add()
    elif kind == "uv_sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16)
    elif kind == "plane":
        bpy.ops.mesh.primitive_plane_add()
    elif kind == "cone":
        bpy.ops.mesh.primitive_cone_add()
    elif kind == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add()
    else:
        raise ValueError(f"Unknown object: {kind}")
    return bpy.context.object


def set_pose(obj, pose):
    if "location" in pose:
        obj.location = vector3(pose["location"])
    if "rotation_degrees" in pose:
        obj.rotation_euler = rotation(pose["rotation_degrees"])
    if "scale" in pose:
        obj.scale = vector3(pose["scale"], (1, 1, 1))


def keyframe_object(obj, spec):
    frames = spec.get("keyframes", [])
    if not isinstance(frames, list):
        raise ValueError("keyframes must be a list")
    for frame in frames:
        at = int(frame["frame"])
        if at < 1:
            raise ValueError("keyframe number must be positive")
        set_pose(obj, frame)
        for path in ("location", "rotation_euler", "scale"):
            obj.keyframe_insert(data_path=path, frame=at)


def create_object(spec, root):
    name = str(spec.get("name", spec["type"]))
    kind = spec["type"]
    if kind == "import":
        source = (root / spec["source"]).resolve()
        if root not in source.parents or not source.is_file():
            raise ValueError("Imported asset must be a project-local existing file")
        new_objects = import_model(source)
        if not new_objects:
            raise RuntimeError(f"Blender did not import any objects: {source}")
        controller = bpy.data.objects.new(name + " control", None)
        bpy.context.collection.objects.link(controller)
        # Parent only top-level imported objects so armatures keep their hierarchy.
        created = set(new_objects)
        for obj in new_objects:
            if obj.parent not in created:
                transform = obj.matrix_world.copy()
                obj.parent = controller
                obj.matrix_world = transform
        target = controller
    else:
        target = primitive(kind)
        target.name = name
        if isinstance(spec.get("material"), dict) and target.type == "MESH":
            target.data.materials.append(create_material(spec["material"], name))
        if target.type == "MESH":
            for poly in target.data.polygons:
                poly.use_smooth = kind not in ("cube", "plane")
    set_pose(target, spec)
    keyframe_object(target, spec)
    return target


def create_scene(recipe, root, blend):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = int(recipe["frames"])
    scene.render.fps = int(recipe["fps"])
    scene.render.resolution_x = int(recipe["width"])
    scene.render.resolution_y = int(recipe["height"])
    scene.render.resolution_percentage = 100
    selected = recipe.get("render_engine", "EEVEE").upper()
    if selected == "CYCLES":
        scene.render.engine = "CYCLES"
        scene.cycles.samples = int(recipe.get("cycles_samples", 32))
        # Some Linux Blender distro builds omit OpenImageDenoiser entirely.
        # Do not fail the full render when that optional component is missing.
        if hasattr(scene.cycles, "use_preview_denoising"):
            scene.cycles.use_preview_denoising = False
        for layer in scene.view_layers:
            if hasattr(layer, "cycles") and hasattr(layer.cycles, "use_denoising"):
                layer.cycles.use_denoising = False
    else:
        try:
            scene.render.engine = "BLENDER_EEVEE_NEXT"
        except TypeError:
            scene.render.engine = "BLENDER_EEVEE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False

    if scene.world is None:
        scene.world = bpy.data.worlds.new("Saseok world")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value = (0.22, 0.27, 0.35, 1.0)
        bg.inputs["Strength"].default_value = 0.45

    for item in recipe.get("objects", []):
        create_object(item, root)

    for item in recipe.get("lights", []):
        kind = str(item.get("type", "AREA")).upper()
        if kind not in ("POINT", "AREA", "SUN", "SPOT"):
            raise ValueError("Unsupported light type")
        light = bpy.data.lights.new(str(item.get("name", "Light")), type=kind)
        light.energy = float(item.get("energy", 1000))
        if kind == "AREA":
            light.shape = "DISK"
            light.size = float(item.get("size", 5))
        obj = bpy.data.objects.new(light.name, light)
        bpy.context.collection.objects.link(obj)
        obj.location = vector3(item.get("location", [3, -4, 7]))
        if "target" in item:
            look_at(obj, item["target"])

    camera = recipe["camera"]
    cam_data = bpy.data.cameras.new("Saseok camera")
    cam = bpy.data.objects.new("Saseok camera", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = vector3(camera.get("location", [6, -9, 6]))
    cam_data.lens = float(camera.get("focal_length_mm", 38))
    look_at(cam, camera.get("target", [0, 0, 1]))
    scene.camera = cam
    keyframe_object(cam, camera)
    scene.frame_set(1)

    # Pack available images/textures into the Blender project when possible.
    try:
        bpy.ops.file.pack_all()
    except RuntimeError:
        pass
    blend.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend))
    print(f"3D BLEND CREATED: {blend}", flush=True)


def render_frame(scene, output):
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.parent / ("." + output.stem + ".partial.png")
    try:
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(temp)
        bpy.ops.render.render(write_still=True)
        if not temp.is_file() or temp.stat().st_size < 500:
            raise RuntimeError(f"Blender produced an invalid frame: {output}")
        os.replace(temp, output)
    finally:
        temp.unlink(missing_ok=True)
    print(f"RENDERED_FRAME {scene.frame_current} {output}", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("build", "preview", "frames"), required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--blend", type=Path, required=True)
    parser.add_argument("--frames-dir", type=Path, required=True)
    parser.add_argument("--preview", type=Path, required=True)
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=1)
    blender_args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    args = parser.parse_args(blender_args)

    root = args.project_root.resolve()
    spec = json.loads(args.recipe.read_text(encoding="utf-8"))
    if args.mode == "build":
        create_scene(spec, root, args.blend)
        return

    scene = bpy.context.scene
    if scene.camera is None:
        raise RuntimeError("The Blender file has no active camera")
    if args.mode == "preview":
        scene.frame_set(1)
        old = scene.render.resolution_percentage
        scene.render.resolution_percentage = 50
        try:
            render_frame(scene, args.preview)
        finally:
            scene.render.resolution_percentage = old
        return

    if not (1 <= args.start <= args.end <= int(spec["frames"])):
        raise ValueError("Render frame range is invalid")
    for frame in range(args.start, args.end + 1):
        scene.frame_set(frame)
        render_frame(scene, args.frames_dir / f"frame_{frame:06d}.png")


if __name__ == "__main__":
    main()
