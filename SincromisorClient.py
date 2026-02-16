import logging
import asyncio
import json
from asyncio import AbstractEventLoop, Event
from aiortc import AudioStreamTrack, RTCDataChannel
from src.SincromisorClient import (
    AudioSenderTrack,
    AudioPlayer,
    SincromisorRTCClient,
    SincromisorClientConfig,
)
from multiprocessing import freeze_support

class CustomizedSincromisorClient(SincromisorRTCClient):
    async def text_ch_on_message(self, channel: RTCDataChannel, message: str) -> None:
        print([channel.label, json.loads(message)])

    async def telop_ch_on_message(self, channel: RTCDataChannel, message: str) -> None:
        print([channel.label, json.loads(message)])


if __name__ == "__main__":
    freeze_support()
    aiortc_logger = logging.getLogger("aiortc")
    aiortc_logger.setLevel(logging.WARNING)
    aioice_logger = logging.getLogger("aioice.ice")
    aioice_logger.setLevel(logging.WARNING)
    logging.basicConfig(level=logging.INFO)  # , filename='sincromisor-client.log')
    logger: logging.Logger = logging.getLogger("SincromisorClient")

    config = SincromisorClientConfig.from_yaml("config.yml")
    print(config)
    shutdown_event: Event = Event()

    audio_sender_track: AudioStreamTrack = AudioSenderTrack(
        channels=config.sender_device.channels,
        samplerate=config.sender_device.samplerate,
        dtype=config.sender_device.dtype,
        blocksize=config.sender_device.blocksize,
        device=config.sender_device.device,
        shutdown_event=shutdown_event,
    )

    audio_player: AudioPlayer = AudioPlayer(
        channels=config.receiver_device.channels,
        samplerate=config.receiver_device.samplerate,
        dtype=config.receiver_device.dtype,
        blocksize=config.receiver_device.blocksize,
        device=config.receiver_device.device,
    )

    scli: SincromisorRTCClient = CustomizedSincromisorClient(
        audio_sender_track=audio_sender_track,
        audio_player=audio_player,
        offer_url=config.offer_url,
        candidate_url=config.resolved_candidate_url,
        ice_server=config.ice_server,
        talk_mode=config.talk_mode,
        shutdown_event=shutdown_event,
    )

    try:
        loop: AbstractEventLoop = asyncio.get_event_loop()
        loop.run_until_complete(scli.run())
    except KeyboardInterrupt:
        pass

    logger.info("send ShutdownEvent")
    shutdown_event.set()
    logger.info("close SincromisorClient")
    loop.run_until_complete(scli.close())
    logger.info("close SenderTrack")
    audio_sender_track.close()
    logger.info("close AudioPlayer")
    audio_player.close()
    loop.close()
    print("done.")
