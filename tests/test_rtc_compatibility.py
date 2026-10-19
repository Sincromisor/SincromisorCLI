"""現行RTC契約を音声デバイスなしで確認する。"""

import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, Mock, PropertyMock, patch
from uuid import UUID

from aiortc import AudioStreamTrack

from src.SincromisorClient import SincromisorClientConfig, SincromisorRTCClient


class ConfigTests(unittest.TestCase):
    def test_server_config_accepts_empty_ice_servers(self):
        data = {
            "config_url": "http://localhost:8080/api/v1/RTCSignalingServer/config.json",
            "talk_mode": "sincro",
            "sender_device": dict(
                channels=1,
                samplerate=48000,
                dtype="int16",
                blocksize=960,
                device="test",
            ),
            "receiver_device": dict(
                channels=2,
                samplerate=48000,
                dtype="int16",
                blocksize=960,
                device="test",
            ),
        }
        response = Mock()
        response.json.return_value = {
            "offerURL": "/api/v1/RTCSignalingServer/offer",
            "candidateURL": "/api/v1/RTCSignalingServer/candidate",
            "iceServers": [],
        }
        with patch("requests.get", return_value=response):
            config = SincromisorClientConfig(
                **SincromisorClientConfig._merge_signaling_config(data)
            )
        self.assertEqual(config.resolved_ice_servers, [])
        self.assertEqual(
            str(config.offer_url),
            "http://localhost:8080/api/v1/RTCSignalingServer/offer",
        )


class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = SincromisorRTCClient(
            AudioStreamTrack(),
            Mock(),
            "http://localhost/offer",
            "http://localhost/candidate",
            None,
            "echo",
            ice_servers=[],
            shutdown_event=asyncio.Event(),
        )

    async def asyncTearDown(self):
        await self.client.close()

    async def test_data_channels_match_server_contract(self):
        self.assertTrue(self.client.text_ch.ordered)
        self.assertIsNone(self.client.text_ch.maxRetransmits)
        self.assertFalse(self.client.telop_ch.ordered)
        self.assertEqual(self.client.telop_ch.maxRetransmits, 0)

    async def test_candidate_has_answer_revision(self):
        self.client.session_id = "01K1AF2Y0H0000000000000001"
        self.client.offer_revision = 1
        response = Mock(status_code=200)
        with patch("requests.post", return_value=response) as post:
            self.client._SincromisorRTCClient__post_candidate(None)
        self.assertEqual(
            post.call_args.kwargs["json"],
            {
                "session_id": self.client.session_id,
                "offer_revision": 1,
                "candidate": None,
            },
        )

    async def test_offer_http_error_is_reported_and_peer_closed(self):
        response = Mock(status_code=400)
        with patch("requests.post", return_value=response):
            with self.assertRaisesRegex(
                RuntimeError, "Offer response was invalid - 400"
            ):
                await self.client.run()
        self.assertEqual(self.client.rpc.connectionState, "closed")

    async def test_offer_sends_request_identity(self):
        response = Mock(status_code=400)
        with patch("requests.post", return_value=response) as post:
            with self.assertRaises(RuntimeError):
                await self.client.run()
        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["offer_revision"], 1)
        self.assertEqual(
            str(UUID(payload["offer_request_id"])), payload["offer_request_id"]
        )
        self.assertIn("a=candidate:", payload["sdp"])
        self.assertEqual(post.call_args.kwargs["timeout"], 10)

    async def test_invalid_answer_closes_peer(self):
        for answer in (
            {"type": "offer", "offer_revision": 1, "session_id": "session"},
            {"type": "answer", "offer_revision": 2, "session_id": "session"},
            {"type": "answer", "offer_revision": 1, "session_id": None},
        ):
            with self.subTest(answer=answer):
                with (
                    patch.object(
                        self.client.rpc, "createOffer", new_callable=AsyncMock
                    ),
                    patch.object(
                        self.client.rpc, "setLocalDescription", new_callable=AsyncMock
                    ),
                    patch.object(
                        self.client,
                        "_SincromisorRTCClient__post_offer",
                        return_value=answer,
                    ),
                ):
                    with self.assertRaises(ValueError):
                        await self.client.run()
                self.assertEqual(self.client.rpc.connectionState, "closed")

    async def test_candidate_http_error_is_not_ignored(self):
        with patch("requests.post", return_value=Mock(status_code=409)):
            with self.assertRaisesRegex(
                RuntimeError, "Candidate response was invalid - 409"
            ):
                self.client._SincromisorRTCClient__post_candidate(None)

    async def test_failed_ice_exits_run(self):
        with (
            patch.object(
                self.client, "_SincromisorRTCClient__offer", new_callable=AsyncMock
            ),
            patch.object(
                type(self.client.rpc),
                "iceConnectionState",
                new_callable=PropertyMock,
                return_value="failed",
            ),
        ):
            with self.assertRaisesRegex(RuntimeError, "ICE connection failed"):
                await self.client.run()
        self.assertTrue(self.client.shutdown_event.is_set())
        self.assertEqual(self.client.rpc.connectionState, "closed")


@unittest.skipUnless(
    os.environ.get("SINCRO_RTC_TEST_URL"), "実RTCサーバーのURLが未指定"
)
class RTCIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_echo_audio_and_data_channels(self):
        await self.check_media("echo")

    async def test_playback_audio_text_and_telop(self):
        await self.check_media("playback")

    async def check_media(self, mode):
        # 既定AudioStreamTrackの無音を置き換え、返却音声が単なる無音でないことも確認する。
        class ToneTrack(AudioStreamTrack):
            async def recv(self):
                import numpy as np

                frame = await super().recv()
                samples = (
                    np.sin(
                        np.arange(frame.samples) * 2 * np.pi * 440 / frame.sample_rate
                    )
                    * 5000
                ).astype("int16")
                frame.planes[0].update(samples.tobytes())
                return frame

        received = asyncio.Event()

        class Player:
            frames = 0

            def add_frame(self, frame):
                self.frames += 1
                if abs(frame.to_ndarray().astype("int32")).max() > 100:
                    received.set()

        base = os.environ["SINCRO_RTC_TEST_URL"].rstrip("/")
        player = Player()
        client = SincromisorRTCClient(
            ToneTrack(),
            player,
            base + "/offer",
            base + "/candidate",
            None,
            mode,
            ice_servers=[],
            shutdown_event=asyncio.Event(),
        )
        text_received = asyncio.Event()
        telop_received = asyncio.Event()
        messages = {}

        def on_message(label, message, event):
            messages[label] = json.loads(message)
            event.set()

        client.text_ch.on(
            "message", lambda message: on_message("text", message, text_received)
        )
        client.telop_ch.on(
            "message", lambda message: on_message("telop", message, telop_received)
        )
        task = asyncio.create_task(client.run())
        try:
            await asyncio.wait_for(received.wait(), 15)
            if mode == "playback":
                await asyncio.wait_for(
                    asyncio.gather(text_received.wait(), telop_received.wait()), 5
                )
                self.assertIn("speech_id", messages["text"])
                self.assertIn("timestamp", messages["telop"])
                self.assertIn("new_text", messages["telop"])
            self.assertEqual(client.text_ch.readyState, "open")
            self.assertEqual(client.telop_ch.readyState, "open")
            self.assertGreater(player.frames, 0)
            self.assertEqual(client.rpc.connectionState, "connected")
            await asyncio.to_thread(client._SincromisorRTCClient__post_candidate, None)
        finally:
            await client.close()
            await asyncio.wait_for(task, 3)
