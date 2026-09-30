"""Рендер говорящей Евы из VRoid-модели (.vrm) в Blender. Запускается отдельным процессом:

    python youtube/blender/eva_render.py job.json

job.json:
    {"model": "persona/eva.vrm", "width": 720, "height": 1280,
     "scenes": [{"out_dir": "...", "emotion": "joy", "seed": 1,
                 "frames": [{"A": 0.8, "I": 0, "U": 0, "E": 0, "O": 0, "blink": 0}, ...]}]}

Каждый кадр — PNG с прозрачным фоном (frame_0001.png, ...): фон подкладывается потом при монтаже.
Стиль — плоская аниме-заливка с контуром (Workbench): рендерится быстро и без видеокарты.
"""

import json
import math
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

# Стандартные имена VRoid Studio
MOUTH = {"A": "Fcl_MTH_A", "I": "Fcl_MTH_I", "U": "Fcl_MTH_U", "E": "Fcl_MTH_E", "O": "Fcl_MTH_O"}
BLINK = "Fcl_EYE_Close"
EMOTIONS = {
    "neutral": {},
    "joy": {"Fcl_BRW_Joy": 0.7, "Fcl_EYE_Joy": 0.35},
    "fun": {"Fcl_BRW_Fun": 0.7, "Fcl_EYE_Fun": 0.4},
    "sorrow": {"Fcl_BRW_Sorrow": 0.8, "Fcl_EYE_Sorrow": 0.4},
    "surprised": {"Fcl_BRW_Surprised": 0.8, "Fcl_EYE_Surprised": 0.5},
    "angry": {"Fcl_BRW_Angry": 0.6, "Fcl_EYE_Angry": 0.3},
}
ARMS_DOWN = math.radians(72)  # VRoid экспортирует T-позу, опускаем руки


def load_model(path: str):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    with tempfile.TemporaryDirectory() as tmp:
        glb = Path(tmp) / "model.glb"  # .vrm — это glTF-бинарник, просто с другим расширением
        shutil.copyfile(path, glb)
        bpy.ops.import_scene.gltf(filepath=str(glb))
        bpy.ops.file.pack_all()  # текстуры — внутрь сцены, пока временный файл жив
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    keys: dict[str, list] = {}
    for obj in bpy.data.objects:
        if obj.type == "MESH" and obj.data.shape_keys:
            for kb in obj.data.shape_keys.key_blocks:
                keys.setdefault(kb.name, []).append(kb)
    return arm, keys


def set_key(keys, name: str, value: float) -> None:
    for kb in keys.get(name, []):
        kb.value = value


def bone_world(arm, name: str) -> Vector:
    return arm.matrix_world @ arm.pose.bones[name].head


def face_camera(arm) -> None:
    """Модель должна смотреть на -Y. У старых VRM (0.x) она смотрит на +Y — разворачиваем."""
    bones = arm.pose.bones
    if "J_Adj_L_FaceEye" in bones and "J_Bip_C_Head" in bones:
        bpy.context.view_layer.update()
        if bone_world(arm, "J_Adj_L_FaceEye").y > bone_world(arm, "J_Bip_C_Head").y:
            arm.rotation_euler.z += math.pi
            bpy.context.view_layer.update()


def rotate_world(arm, bone: str, axis: tuple, angle: float) -> None:
    """Поворот кости вокруг оси мира — не зависит от того, как кость ориентирована внутри."""
    pb = arm.pose.bones.get(bone)
    if not pb:
        return
    m = arm.matrix_world @ pb.matrix
    pivot = m.to_translation()
    r = Matrix.Translation(pivot) @ Matrix.Rotation(angle, 4, axis) @ Matrix.Translation(-pivot)
    pb.matrix = arm.matrix_world.inverted() @ r @ m
    bpy.context.view_layer.update()


def setup_scene(arm, width: int, height: int):
    scene = bpy.context.scene
    face_camera(arm)
    rotate_world(arm, "J_Bip_L_UpperArm", (0, 1, 0), ARMS_DOWN)
    rotate_world(arm, "J_Bip_R_UpperArm", (0, 1, 0), -ARMS_DOWN)

    head = bone_world(arm, "J_Bip_C_Head")
    scale = head.z / 1.4  # модели бывают разного роста
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = 50
    cam = bpy.data.objects.new("Camera", cam_data)
    scene.collection.objects.link(cam)
    # Кадр по грудь: над макушкой запас под ник канала, снизу — грудь с надписью на худи.
    target = Vector((head.x, head.y, head.z + 0.005 * scale))
    cam.location = Vector((head.x, head.y - 1.05 * scale, head.z + 0.05 * scale))
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam

    scene.render.engine = "BLENDER_WORKBENCH"
    shading = scene.display.shading
    shading.light = "FLAT"
    shading.color_type = "TEXTURE"
    shading.show_object_outline = True
    shading.object_outline_color = (0.08, 0.05, 0.12)
    scene.display.render_aa = "8"
    scene.view_settings.view_transform = "Standard"
    scene.render.film_transparent = True
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    # Базовая поза головы и груди, от которой считаем покачивания.
    # Порядок важен: сначала родители (грудь → шея → голова).
    rest = {b: arm.pose.bones[b].matrix.copy() for b in ("J_Bip_C_UpperChest", "J_Bip_C_Neck", "J_Bip_C_Head")
            if b in arm.pose.bones}
    return scene, rest


def idle_motion(arm, rest: dict, t: float, rng_phase: list, talk: float) -> None:
    """Живость: голова плавно покачивается и кивает в такт речи, грудь «дышит»."""
    for bone, m in rest.items():
        arm.pose.bones[bone].matrix = m
        bpy.context.view_layer.update()
    p = rng_phase
    yaw = 2.5 * math.sin(2 * math.pi * 0.21 * t + p[0]) + 1.0 * math.sin(2 * math.pi * 0.53 * t + p[1])
    pitch = 1.5 * math.sin(2 * math.pi * 0.17 * t + p[2]) - 2.0 * talk
    roll = 2.0 * math.sin(2 * math.pi * 0.13 * t + p[3])
    breath = 0.8 * math.sin(2 * math.pi * 0.25 * t)
    rotate_world(arm, "J_Bip_C_UpperChest", (1, 0, 0), math.radians(breath))
    for bone, share in (("J_Bip_C_Neck", 0.4), ("J_Bip_C_Head", 0.6)):
        rotate_world(arm, bone, (0, 0, 1), math.radians(yaw * share))
        rotate_world(arm, bone, (1, 0, 0), math.radians(pitch * share))
        rotate_world(arm, bone, (0, 1, 0), math.radians(roll * share))


def render_scene(arm, keys, scene, rest, job: dict, fps: float) -> None:
    out = Path(job["out_dir"])
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(job.get("seed", 0))
    phase = [rng.uniform(0, 2 * math.pi) for _ in range(4)]
    emotion = EMOTIONS.get(job.get("emotion", "neutral"), {})
    for name in {n for e in EMOTIONS.values() for n in e}:
        set_key(keys, name, 0.0)
    for i, frame in enumerate(job["frames"]):
        for shape, key in MOUTH.items():
            set_key(keys, key, frame.get(shape, 0.0))
        blink = frame.get("blink", 0.0)
        set_key(keys, BLINK, blink)
        for name, weight in emotion.items():  # при моргании глазные эмоции приглушаем, чтобы веки не «ломались»
            set_key(keys, name, weight * (1 - blink) if "_EYE_" in name else weight)
        talk = max(frame.get(s, 0.0) for s in MOUTH)
        idle_motion(arm, rest, i / fps, phase, talk)
        scene.render.filepath = str(out / f"frame_{i + 1:04d}.png")
        bpy.ops.render.render(write_still=True)


def render_still(model: str, out: str, width: int, height: int, background=(0.12, 0.08, 0.2)) -> None:
    """Один портрет Евы на цветном фоне — эталон лица для генерации остальных кадров."""
    arm, keys = load_model(model)
    scene, _ = setup_scene(arm, width, height)
    scene.render.film_transparent = False
    world = bpy.data.worlds.new("World")
    scene.world = world
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = background
    world.color = background
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)


def main() -> None:
    job = json.loads(Path(sys.argv[-1]).read_text(encoding="utf-8"))
    if job.get("still"):
        render_still(job["model"], job["still"], job["width"], job["height"])
        return
    arm, keys = load_model(job["model"])
    missing = [k for k in (*MOUTH.values(), BLINK) if k not in keys]
    if missing:
        print(f"ВНИМАНИЕ: в модели нет форм {missing} — губы/моргание будут неполными", flush=True)
    scene, rest = setup_scene(arm, job["width"], job["height"])
    for scene_job in job["scenes"]:
        render_scene(arm, keys, scene, rest, scene_job, job.get("fps", 12))
        print(f"готово: {scene_job['out_dir']} ({len(scene_job['frames'])} кадров)", flush=True)


if __name__ == "__main__":
    main()
    # bpy иногда падает при выгрузке после рендера, когда всё уже записано, — выходим сразу.
    sys.stdout.flush()
    os._exit(0)
