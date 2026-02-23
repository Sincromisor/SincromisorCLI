import yaml
import requests
import sounddevice as sd

from enum import Enum
from urllib.parse import urljoin
from pydantic import BaseModel, HttpUrl, Field, field_validator, model_validator, ConfigDict


class AudioDeviceConfig(BaseModel):
    channels: int
    samplerate: int
    dtype: str
    blocksize: int
    device: str | None = Field(default=None)

    @classmethod
    def default_device(cls) -> str | None:
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
    def default_device(cls) -> str | None:
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
    def default_device(cls) -> str | None:
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


class RTCIceServerConfig(BaseModel):
    # Sincromisor config.json の iceServers (WebRTC標準形式) をそのまま受け取る。
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    urls: str | list[str]
    username: str | None = None
    credential: str | None = None
    credential_type: str | None = Field(default=None, alias="credentialType")

    def to_aiortc_kwargs(self) -> dict:
        return {
            "urls": self.urls,
            "username": self.username,
            "credential": self.credential,
        }


class SincromisorClientConfig(BaseModel):
    # Sincromisor本体の config.json (例: /api/v1/RTCSignalingServer/config.json) を指定すると、
    # offer/candidate/ICE設定を自動同期できる。
    config_url: HttpUrl | None = None
    offer_url: HttpUrl | None = None
    candidate_url: HttpUrl | None = None
    # 後方互換: 単一STUN/TURN URL指定
    ice_server: str | None = None
    # 現行Sincromisor config.json互換: WebRTC標準形式の複数ICEサーバー定義
    ice_servers: list[RTCIceServerConfig] | None = None
    talk_mode: SincromisorTalkMode
    sender_device: AudioInputDeviceConfig
    receiver_device: AudioOutputDeviceConfig

    @model_validator(mode="after")
    def validate_signaling_settings(self):
        if self.offer_url is None:
            raise ValueError("offer_url is required (or specify config_url).")
        if not self.ice_server and not self.ice_servers:
            raise ValueError("ice_server or ice_servers is required (or specify config_url).")
        return self

    @property
    def resolved_candidate_url(self) -> str:
        if self.candidate_url is not None:
            return str(self.candidate_url)
        if self.offer_url is None:
            raise ValueError("offer_url is not resolved.")
        offer_url = str(self.offer_url)
        if offer_url.endswith("/offer"):
            return offer_url[:-len("/offer")] + "/candidate"
        return offer_url.rstrip("/") + "/candidate"

    @property
    def resolved_ice_servers(self) -> list[dict]:
        if self.ice_servers:
            return [ice_server.to_aiortc_kwargs() for ice_server in self.ice_servers]
        if self.ice_server:
            return [{"urls": self.ice_server}]
        raise ValueError("ice_server(s) is not resolved.")

    @classmethod
    def _merge_signaling_config(cls, data: dict) -> dict:
        config_url = data.get("config_url")
        if not config_url:
            return data

        response = requests.get(str(config_url), timeout=10)
        response.raise_for_status()
        server_config = response.json()
        base_url = str(config_url)

        # config.yml 明示指定を優先し、未指定値のみ config.json から補完する。
        if "offer_url" not in data and "offerURL" in server_config:
            data["offer_url"] = urljoin(base_url, server_config["offerURL"])
        if "candidate_url" not in data and "candidateURL" in server_config:
            data["candidate_url"] = urljoin(base_url, server_config["candidateURL"])
        if (
            "ice_servers" not in data
            and "ice_server" not in data
            and "iceServers" in server_config
        ):
            data["ice_servers"] = server_config["iceServers"]

        return data

    @classmethod
    def from_yaml(cls, yaml_path) -> "SincromisorClientConfig":
        with open(yaml_path, "r") as file:
            data = yaml.safe_load(file)
            data = cls._merge_signaling_config(data)
            return SincromisorClientConfig(**data)
