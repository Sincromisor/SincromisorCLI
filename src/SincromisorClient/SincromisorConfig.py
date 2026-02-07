import yaml
import sounddevice as sd

from enum import Enum
from pydantic import BaseModel, HttpUrl, Field, field_validator


class AudioDeviceConfig(BaseModel):
    channels: int
    samplerate: int
    dtype: str
    blocksize: int
    device: str | None = Field(default=None)

    @classmethod
    def default_device(cls) -> str:
        return None

    @field_validator("device", mode="before")
    def set_default_device(cls, value):
        if value is None:
            return cls.default_device()
        return value

    @field_validator("device", mode="after")
    def check_default_device(cls, value):
        if value is None:
            raise ValueError("No audio device.")
        return value

    @field_validator("samplerate", mode="before")
    def default_samplerate(cls, value):
        if value != 48000:
            raise ValueError("samplerate must be 48000.")
        return value

    @field_validator("dtype", mode="before")
    def default_dtype(cls, value):
        if value != "int16":
            raise ValueError("dtype must be int16.")
        return value

    @field_validator("blocksize", mode="before")
    def default_blocksize(cls, value):
        if value != 960:
            raise ValueError("blocksize must be 960.")
        return value


class AudioInputDeviceConfig(AudioDeviceConfig):
    @classmethod
    def default_device(cls) -> str:
        default_device: int = sd.default.device[0]
        if default_device < 0:
            return None
        return (
            sd.query_devices()[default_device]["name"]
            + ", "
            + sd.query_hostapis()[sd.default.hostapi]["name"]
        )

    @field_validator("channels", mode="before")
    def default_dtype(cls, value):
        if value != 1:
            raise ValueError("input channels must be 1.")
        return value


class AudioOutputDeviceConfig(AudioDeviceConfig):
    @classmethod
    def default_device(cls) -> str:
        default_device: int = sd.default.device[1]
        if default_device < 0:
            return None
        return (
            sd.query_devices()[default_device]["name"]
            + ", "
            + sd.query_hostapis()[sd.default.hostapi]["name"]
        )

    @field_validator("channels", mode="before")
    def default_dtype(cls, value):
        if value != 2:
            raise ValueError("output channels must be 2.")
        return value

class SincromisorTalkMode(str, Enum):
    chat = 'chat'
    sincro = 'sincro'

class SincromisorClientConfig(BaseModel):
    offer_url: HttpUrl
    ice_server: str
    talk_mode: SincromisorTalkMode
    sender_device: AudioInputDeviceConfig
    receiver_device: AudioOutputDeviceConfig

    @classmethod
    def from_yaml(cls, yaml_path) -> "SincromisorClientConfig":
        with open(yaml_path, "r") as file:
            data = yaml.safe_load(file)
            return SincromisorClientConfig(**data)
