"""Configuration settings for the guga 3D desktop pet application."""

from dataclasses import dataclass

@dataclass
class WindowConfig:
    width: int = 400
    height: int = 500
    title: str = "guga"
    bg_color: tuple = (0.0, 0.0, 0.0, 0.0)  # transparent
    transparent: bool = True

@dataclass
class PetConfig:
    idle_bob_amplitude: float = 0.015
    idle_bob_speed: float = 2.5
    sleep_timeout: float = 120.0

@dataclass
class CameraConfig:
    fov: float = 40.0
    near: float = 0.1
    far: float = 100.0
    distance: float = 3.5
    pitch: float = -10.0

window = WindowConfig()
pet = PetConfig()
camera = CameraConfig()

MODEL_DIR = "../3d_models"
MODEL_FILE = "character.vrm"