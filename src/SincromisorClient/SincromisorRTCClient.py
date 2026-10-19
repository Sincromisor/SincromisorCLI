"""CLIの音声トラックとDataChannelを、HTTPシグナリングでRTCサーバーへ接続する。"""

import json
import asyncio
from asyncio import Event
import logging
import requests
from typing import Any
from uuid import uuid4
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    RTCIceServer,
    AudioStreamTrack,
    RTCDataChannel,
    MediaStreamTrack,
    RTCIceCandidate,
)
from aiortc.sdp import candidate_to_sdp
from aiortc.mediastreams import MediaStreamError
from av.audio.frame import AudioFrame
from . import AudioPlayer


class SincromisorRTCClient:
    """音声と2本のDataChannelを接続し、終了時にPeerConnectionを回収する。"""

    def __init__(
        self,
        audio_sender_track: AudioStreamTrack,
        audio_player: AudioPlayer,
        offer_url: str,
        candidate_url: str,
        ice_server: str | None,
        talk_mode: str,
        ice_servers: list[dict[str, Any]] | None = None,
        shutdown_event: Event | None = None,
    ):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.offer_url: str = offer_url
        self.candidate_url: str = candidate_url
        self.ice_server: str | None = ice_server
        self.ice_servers: list[dict[str, Any]] | None = ice_servers
        self.talk_mode: str = talk_mode
        self.shutdown_event: Event = (
            shutdown_event if shutdown_event is not None else Event()
        )
        self.session_id: str | None = None
        self.offer_request_id: str = str(uuid4())
        self.offer_revision: int = 1
        self.pending_ice_candidates: list[dict | None] = []
        self.rpc: RTCPeerConnection = RTCPeerConnection(
            configuration=RTCConfiguration(
                iceServers=self.__build_ice_servers(
                    ice_server=self.ice_server,
                    ice_servers=self.ice_servers,
                )
            )
        )
        self.player: AudioPlayer = audio_player
        self.rpc.addTrack(audio_sender_track)
        self.__setup_receiver_track()
        self.text_ch: RTCDataChannel = self.__setup_text_ch()
        self.telop_ch: RTCDataChannel = self.__setup_telop_ch()
        self.current_ice_state: str = ""
        self.__setup_icecandidate()

    def __build_ice_servers(
        self,
        ice_server: str | None,
        ice_servers: list[dict[str, Any]] | None,
    ) -> list[RTCIceServer]:
        if ice_servers:
            servers: list[RTCIceServer] = []
            for conf in ice_servers:
                # Sincromisor config.json の iceServers を aiortc 用オブジェクトへ変換する。
                servers.append(
                    RTCIceServer(
                        urls=conf["urls"],
                        username=conf.get("username"),
                        credential=conf.get("credential"),
                    )
                )
            return servers
        if ice_server:
            return [RTCIceServer(ice_server)]
        return []

    async def run(self) -> None:
        """接続失敗は呼出元へ返し、停止通知・ICE失敗・例外時に接続を閉じる。"""
        try:
            await self.__offer()
            while not self.shutdown_event.is_set():
                if self.current_ice_state != self.rpc.iceConnectionState:
                    self.logger.info(f"ICE Status: {self.rpc.iceConnectionState}")
                    self.current_ice_state = self.rpc.iceConnectionState
                if self.rpc.iceConnectionState == "failed":
                    raise RuntimeError("ICE connection failed")
                if self.rpc.iceConnectionState == "closed":
                    break
                await asyncio.sleep(1)
        finally:
            await self.close()

    def __setup_receiver_track(self) -> None:
        @self.rpc.on("track")
        async def on_track(track: MediaStreamTrack):
            self.logger.info(["on_track", track.kind, track])
            try:
                while not self.shutdown_event.is_set():
                    frame: AudioFrame = await track.recv()
                    self.player.add_frame(frame)
            except MediaStreamError as e:
                self.logger.warning(["MediaStreamError", e])
            except Exception as e:
                self.logger.error(["UnknownError", e])
            self.logger.info("close RTC track")
            track.stop()

    def __setup_text_ch(self) -> RTCDataChannel:
        text_ch: RTCDataChannel = self.rpc.createDataChannel("text_ch")
        text_ch.on(
            "message",
            lambda message: asyncio.create_task(
                self.text_ch_on_message(text_ch, message)
            ),
        )
        text_ch.on("open", lambda: asyncio.create_task(self.text_ch_on_open(text_ch)))
        text_ch.on("close", lambda: asyncio.create_task(self.text_ch_on_close(text_ch)))
        return text_ch

    def __setup_telop_ch(self) -> RTCDataChannel:
        # テロップは欠落を許容し、再送による古い口形の遅着を避ける契約。
        telop_ch: RTCDataChannel = self.rpc.createDataChannel(
            "telop_ch", ordered=False, maxRetransmits=0
        )
        telop_ch.on(
            "message",
            lambda message: asyncio.create_task(
                self.telop_ch_on_message(telop_ch, message)
            ),
        )
        telop_ch.on(
            "open", lambda: asyncio.create_task(self.telop_ch_on_open(telop_ch))
        )
        telop_ch.on(
            "close", lambda: asyncio.create_task(self.telop_ch_on_close(telop_ch))
        )
        return telop_ch

    async def __offer(self) -> None:
        offer: RTCSessionDescription = await self.rpc.createOffer()
        # aiortcはここでICE候補の収集を完了し、候補を含むSDPを生成する。
        await self.rpc.setLocalDescription(offer)
        # 同期HTTPの待機中もICE/DTLSと音声処理を進める。
        answer = await asyncio.to_thread(self.__post_offer)
        if answer.get("type") != "answer" or answer.get("offer_revision") != 1:
            raise ValueError("Invalid answer type or offer_revision")
        if not isinstance(answer.get("session_id"), str) or not answer["session_id"]:
            raise ValueError("Missing answer session_id")
        self.session_id = answer["session_id"]
        self.offer_revision = answer["offer_revision"]
        await self.rpc.setRemoteDescription(
            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
        )
        await self.__flush_pending_ice_candidates()
        self.logger.info("RTC answer applied: session_id=%s", self.session_id)

    def __post_offer(self) -> dict:
        # 初回Offerを識別し、HTTPの失敗はrunへ返して接続を回収する。
        response = requests.post(
            self.offer_url,
            json={
                "sdp": self.rpc.localDescription.sdp,
                "type": self.rpc.localDescription.type,
                "talk_mode": self.talk_mode,
                "offer_request_id": self.offer_request_id,
                "offer_revision": self.offer_revision,
            },
            timeout=10,
        )
        if response.status_code != 200:
            msg = f"Offer response was invalid - {response.status_code}"
            self.logger.error(msg)
            raise RuntimeError(msg)
        return response.json()

    def __setup_icecandidate(self) -> None:
        @self.rpc.on("icecandidate")
        async def on_icecandidate(candidate: RTCIceCandidate | None):
            try:
                await self.__send_ice_candidate(
                    self.__serialize_ice_candidate(candidate)
                )
            except Exception:
                self.logger.exception("ICE candidate delivery failed")
                await self.close()

    def __serialize_ice_candidate(
        self, candidate: RTCIceCandidate | None
    ) -> dict | None:
        if candidate is None:
            return None
        candidate_sdp = candidate_to_sdp(candidate).strip()
        if candidate_sdp == "":
            return None
        return {
            "candidate": f"candidate:{candidate_sdp}",
            "sdpMid": candidate.sdpMid,
            "sdpMLineIndex": candidate.sdpMLineIndex,
        }

    async def __flush_pending_ice_candidates(self) -> None:
        # Answer適用前の候補は、確定したセッションIDと改訂番号で送る。
        pending = self.pending_ice_candidates
        self.pending_ice_candidates = []
        for candidate in pending:
            await self.__send_ice_candidate(candidate)

    async def __send_ice_candidate(self, candidate: dict | None) -> None:
        if self.session_id is None:
            self.pending_ice_candidates.append(candidate)
            return
        await asyncio.to_thread(self.__post_candidate, candidate)

    def __post_candidate(self, candidate: dict | None) -> None:
        # Noneは候補収集完了を表し、通常候補と同じ改訂番号を必須とする。
        response = requests.post(
            self.candidate_url,
            json={
                "session_id": self.session_id,
                "offer_revision": self.offer_revision,
                "candidate": candidate,
            },
            timeout=5,
        )
        if response.status_code != 200:
            # 必須候補を失った接続を継続しない。runのfinallyでも安全に再度closeできる。
            raise RuntimeError(
                f"Candidate response was invalid - {response.status_code}"
            )

    # データチャンネルに動きがあった際のイベントハンドラ。
    # ここをoverrideしていろいろやるとよいと思います。
    async def telop_ch_on_message(self, channel: RTCDataChannel, message: str) -> None:
        data = json.loads(message)
        self.logger.info(f"{channel.label}: {data}")

    async def telop_ch_on_open(self, channel: RTCDataChannel) -> None:
        self.logger.info(f"Data channel {channel.label} opened")

    async def telop_ch_on_close(self, channel: RTCDataChannel) -> None:
        self.logger.info(f"Data channel {channel.label} closed")

    async def text_ch_on_message(self, channel: RTCDataChannel, message: str) -> None:
        data = json.loads(message)
        self.logger.info(f"{channel.label}: {data}")

    async def text_ch_on_open(self, channel: RTCDataChannel) -> None:
        self.logger.info(f"Data channel {channel.label} opened")

    async def text_ch_on_close(self, channel: RTCDataChannel) -> None:
        self.logger.info(f"Data channel {channel.label} closed")

    async def close(self):
        """停止通知とチャネル終了を行う。録音・再生デバイスは呼出元が閉じる。"""
        if not self.shutdown_event.is_set():
            self.shutdown_event.set()
        self.logger.info("telop_ch is closing...")
        self.telop_ch.close()
        self.logger.info("text_ch is closing...")
        self.text_ch.close()
        self.logger.info("RTCSession is closing...")
        await self.rpc.close()
        self.logger.info("RTCSession is closed.")
