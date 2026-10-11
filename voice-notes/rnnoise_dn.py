#!/usr/bin/env python3
"""نویزگیری با RNNoise (دور زدن باگ pyrnnoise.denoise_wav)."""
import numpy as np, soundfile as sf, sys
from pyrnnoise import RNNoise

def denoise_array(x_i16: np.ndarray, sr: int = 16000, chunk_sec: float = 10.0) -> np.ndarray:
    d = RNNoise(sample_rate=sr)
    n = int(chunk_sec * sr)
    outs = []
    for i in range(0, len(x_i16), n):
        chunk = x_i16[i:i + n]
        last = (i + n) >= len(x_i16)
        for _prob, frame in d.denoise_chunk(chunk, partial=last):
            outs.append(np.asarray(frame).reshape(-1))
    if not outs:
        return x_i16
    return np.concatenate(outs).astype(np.int16)

def denoise_file(src: str, dst: str) -> None:
    x, sr = sf.read(src, dtype='int16', always_2d=False)
    if x.ndim > 1:
        x = x.mean(axis=1).astype(np.int16)
    y = denoise_array(x, sr)
    sf.write(dst, y, sr, subtype='PCM_16')

if __name__ == '__main__':
    denoise_file(sys.argv[1], sys.argv[2])
    print('ok', sys.argv[2])
