import sounddevice as sd
import numpy as np
import sys
from queue import Queue, Empty
from av.audio.frame import AudioFrame


class AudioPlayer:
    def __init__(
        self,
        channels: int = 2,
        samplerate: int = 48000,
        dtype: str = "int16",
        blocksize: int = 960,
        device: str = "default",
    ):
        self.start_idx: int = 0
        self.channels: int = channels
        self.samplerate: int = samplerate
        self.dtype: str = dtype
        self.device: str = device
        self.blocksize: int = blocksize
        self.queue: Queue = Queue(3)
        self.audio_output = sd.OutputStream(
            channels=self.channels,
            samplerate=self.samplerate,
            dtype=self.dtype,
            blocksize=self.blocksize,
            device=self.device,
            callback=self.__callback,
        )
        self.started: bool = False
        print("start AudioPlayer")

    def __callback(
        self, outdata: np.ndarray, frames: int, time, status: sd.CallbackFlags
    ) -> None:
        outdata.fill(0)
        try:
            frame: np.ndarray = self.queue.get_nowait()
        except Empty:
            return
        outdata[:] = frame.reshape((self.blocksize, self.channels))

    def add_frame(self, frame: AudioFrame):
        array = frame.to_ndarray()
        self.queue.put(array)
        self.__ensure_started()

    def add_numpy_frame(self, frame: np.ndarray):
        self.queue.put(frame)
        self.__ensure_started()

    def __ensure_started(self) -> None:
        if self.started:
            return
        self.audio_output.start()
        self.started = True

    def close(self):
        if self.started:
            self.audio_output.stop()
        self.audio_output.close()


if __name__ == "__main__":
    from SincromisorClient.SquareWave import SquareWave

    try:
        square_wave = SquareWave()
        ap = AudioPlayer(blocksize=960)
        while True:
            ap.add_numpy_frame(square_wave.generate(960))
    except KeyboardInterrupt:
        sys.exit(1)
