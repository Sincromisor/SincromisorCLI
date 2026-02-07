import json
import asyncio
from asyncio import Event
import logging
import requests
from aiortc import (
    RTCPeerConnection,
    RTCSessionDescription,
    RTCConfiguration,
    RTCIceServer,
    AudioStreamTrack,
    RTCDataChannel,
    MediaStreamTrack,
)
from aiortc.mediastreams import MediaStreamError
from av.audio.frame import AudioFrame
from . import AudioPlayer


class SincromisorRTCClient:
    # talk_mode: chat, sincro
    def __init__(
        self,
        audio_sender_track: AudioStreamTrack,
        audio_player: AudioPlayer,
        offer_url: str,
        ice_server: str,
        talk_mode: str,
        shutdown_event: Event = Event(),
    ):
        self.logger: logging.Logger = logging.getLogger(__name__)
        self.offer_url: str = offer_url
        self.ice_server: str = ice_server
        self.talk_mode: str = talk_mode
        self.shutdown_event: Event = shutdown_event
        self.rpc: RTCPeerConnection = RTCPeerConnection(
            configuration=RTCConfiguration(iceServers=[RTCIceServer(self.ice_server)])
        )
        self.player: AudioPlayer = audio_player
        self.rpc.addTrack(audio_sender_track)
        self.__setup_receiver_track()
        self.text_ch: RTCDataChannel = self.__setup_text_ch()
        self.telop_ch: RTCDataChannel = self.__setup_telop_ch()
        self.current_ice_state:str = ''

    async def run(self) -> None:
        await self.__offer()
        while True:
            if self.current_ice_state != self.rpc.iceConnectionState:
                self.logger.info(f'ICE Status: {self.rpc.iceConnectionState}')
                self.current_ice_state = self.rpc.iceConnectionState

            match self.rpc.iceConnectionState:
                case "checking" | "connected" | "completed":
                    pass
                case "closed":
                    self.shutdown_event.set()
                    break
                case _:
                    self.logger.info(["iceConnectionState", self.rpc.iceConnectionState])
            await asyncio.sleep(1)

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
        telop_ch: RTCDataChannel = self.rpc.createDataChannel("telop_ch")
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
        # setLocalDescriptionしてローカル側のOfferSDPをつくってからサーバーに投げる
        await self.rpc.setLocalDescription(offer)
        self.logger.info(
            [self.rpc.localDescription.type, self.rpc.localDescription.sdp]
        )
        answer = self.__post_offer()
        await self.rpc.setRemoteDescription(
            RTCSessionDescription(sdp=answer["sdp"], type=answer["type"])
        )
        self.logger.info(
            [self.rpc.remoteDescription.type, self.rpc.remoteDescription.sdp]
        )

    def __post_offer(self) -> dict:
        response = requests.post(
            self.offer_url,
            json={
                "sdp": self.rpc.localDescription.sdp,
                "type": self.rpc.localDescription.type,
                "talk_mode": self.talk_mode,
            },
        )
        if response.status_code != 200:
            msg = f"Offer response was invalid - {response.status_code}"
            self.logger.error(msg)
            raise msg
        return response.json()

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
        if not self.shutdown_event.is_set():
            self.shutdown_event.set()
        self.logger.info("telop_ch is closing...")
        self.telop_ch.close()
        self.logger.info("text_ch is closing...")
        self.text_ch.close()
        self.logger.info("RTCSession is closing...")
        await self.rpc.close()
        self.logger.info("RTCSession is closed.")
