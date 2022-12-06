import av
import time
import threading
import logging
import tkinter as tk
from PIL import ImageTk, Image, ImageOps
from typing import Tuple, Dict
import sounddevice as sd

logging.getLogger('libav').setLevel(logging.ERROR)


class TkinterVideo(tk.Label):

    def __init__(self, master, scaled: bool = True, consistant_frame_rate: bool = True, keep_aspect: bool = False,
                 *args, **kwargs):
        super(TkinterVideo, self).__init__(master, *args, **kwargs)
        self.path = ""
        self._load_thread = None

        self._paused = True
        self._stop = True

        self.consistant_frame_rate = consistant_frame_rate

        self._container = None

        self._current_img = None
        self._current_frame_Tk = None
        self._frame_number = 0
        self._time_stamp = 0

        self._current_frame_size = (0, 0)

        self._seek = False
        self._seek_sec = 0

        self._video_info = {
            "duration": 0,
            "framerate": 0,
            "framesize": (0, 0)
        }

        self.set_scaled(scaled)
        self._keep_aspect_ratio = keep_aspect
        self._resampling_method: int = Image.NEAREST

        self.bind("<<Destroy>>", self.stop)
        self.bind("<<FrameGenerated>>", self._display_frame)

    def keep_aspect(self, keep_aspect: bool):
        self._keep_aspect_ratio = keep_aspect

    def set_resampling_method(self, method: int):
        self._resampling_method = method

    def set_size(self, size: Tuple[int, int], keep_aspect: bool = False):
        self.set_scaled(False, self._keep_aspect_ratio)
        self._current_frame_size = size
        self._keep_aspect_ratio = keep_aspect

    def _resize_event(self, event):

        self._current_frame_size = event.width, event.height

        if self._paused and self._current_img and self.scaled:
            if self._keep_aspect_ratio:
                proxy_img = ImageOps.contain(self._current_img.copy(), self._current_frame_size)

            else:
                proxy_img = self._current_img.copy().resize(self._current_frame_size)

            self._current_imgtk = ImageTk.PhotoImage(proxy_img)
            self.config(image=self._current_imgtk)

    def set_scaled(self, scaled: bool, keep_aspect: bool = False):
        self.scaled = scaled
        self._keep_aspect_ratio = keep_aspect

        if scaled:
            self.bind("<Configure>", self._resize_event)

        else:
            self.unbind("<Configure>")
            self._current_frame_size = self.video_info()["framesize"]

    def _set_frame_size(self, event=None):
        self._video_info["framesize"] = (
        self._container.streams.video[0].width, self._container.streams.video[0].height)

        self.current_imgtk = ImageTk.PhotoImage(Image.new("RGBA", self._video_info["framesize"], (255, 0, 0, 0)))
        self.config(width=150, height=100, image=self.current_imgtk)

    def _load(self, path):
        self.path = path
        current_thread = threading.current_thread()

        with av.open(path) as self._container:

            self._container.streams.video[0].thread_type = "AUTO"

            self._container.fast_seek = True
            self._container.discard_corrupt = True

            video_stream = self._container.streams.video[0]
            self.audio_stream = self._container.streams.get(audio=0)[0]
            sd.play(self.audio_stream, 44100)

            try:
                self._video_info["framerate"] = int(video_stream.average_rate)

            except TypeError:
                raise TypeError("Not a video file")

            try:

                self._video_info["duration"] = float(video_stream.duration * video_stream.time_base)
                self.event_generate("<<Duration>>")

            except (TypeError, tk.TclError):
                pass

            self._frame_number = 0

            self._set_frame_size()

            self.stream_base = video_stream.time_base
            self.audio_stream_base = self.audio_stream.time_base

            try:
                self.event_generate("<<Loaded>>")

            except tk.TclError:
                pass

            now = time.time_ns() // 1_000_000
            then = now

            time_in_frame = (1 / self._video_info["framerate"]) * 1000

            while self._load_thread == current_thread and not self._stop:
                if self._seek:
                    self._container.seek(self._seek_sec * 1000000, whence='time', backward=True, any_frame=False)
                    self._seek = False
                    self._frame_number = self._video_info["framerate"] * self._seek_sec

                    self._seek_sec = 0

                if self._paused:
                    time.sleep(0.0001)
                    continue

                now = time.time_ns() // 1_000_000
                delta = now - then
                then = now
                try:
                    frame = next(self._container.decode(video=0))

                    self._time_stamp = float(frame.pts * video_stream.time_base)

                    self._current_img = frame.to_image()

                    self._frame_number += 1

                    self.event_generate("<<FrameGenerated>>")

                    if self._frame_number % self._video_info["framerate"] == 0:
                        self.event_generate("<<SecondChanged>>")

                    if self.consistant_frame_rate:
                        time.sleep(max((time_in_frame - delta) / 1000, 0))

                except (StopIteration, av.error.EOFError, tk.TclError):
                    break

        self._frame_number = 0
        self._paused = True
        self._load_thread = None

        self._container = None

        try:
            self.event_generate("<<Ended>>")

        except tk.TclError:
            pass

    def load(self, path: str):
        self.stop()
        self.path = path

    def stop(self):
        self._paused = True
        self._stop = True

    def pause(self):
        self._paused = True

    def play(self):
        self._paused = False
        self._stop = False

        if not self._load_thread:
            self._load_thread = threading.Thread(target=self._load, args=(self.path,), daemon=True)
            self._load_thread.start()

    def is_paused(self):
        return self._paused

    def video_info(self) -> Dict:
        return self._video_info

    def metadata(self) -> Dict:
        if self._container:
            return self._container.metadata

        return {}

    def current_frame_number(self) -> int:
        return self._frame_number

    def current_duration(self) -> float:
        return self._time_stamp

    def current_img(self) -> Image:
        return self._current_img

    def _display_frame(self, event):
        if self.scaled or (len(self._current_frame_size) == 2 and all(self._current_frame_size)):

            if self._keep_aspect_ratio:
                self._current_img = ImageOps.contain(self._current_img, self._current_frame_size,
                                                     self._resampling_method)

            else:
                self._current_img = self._current_img.resize(self._current_frame_size, self._resampling_method)

        else:
            self._current_frame_size = self.video_info()["framesize"] if all(self.video_info()["framesize"]) else (1, 1)

            if self._keep_aspect_ratio:
                self._current_img = ImageOps.contain(self._current_img, self._current_frame_size,
                                                     self._resampling_method)

            else:
                self._current_img = self._current_img.resize(self._current_frame_size, self._resampling_method)

        self.current_imgtk = ImageTk.PhotoImage(self._current_img)
        self.config(image=self.current_imgtk)

    def seek(self, sec: int):
        """ seeks to specific time"""

        self._seek = True
        self._seek_sec = sec
