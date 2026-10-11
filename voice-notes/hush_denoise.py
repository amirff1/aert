#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hush_denoise — پورت پایتونیِ نویزگیر عصبی Hush (DeepFilterNet3) از sورس C++
=======================================================================
مرجع: github.com/mah92/hush_cpp  →  src/hush_enhance_onnx.cpp + feature_extract.cc
مدل‌ها: enc.onnx / erb_dec.onnx / df_dec.onnx  (DF3، آموزش‌دیدهٔ Meta، ۸.۸MB)
مشخصات: sr=16000, FFT=320, hop=160, nb_erb=32, nb_df=64, order=5, norm_tau=1.0

استفاده به‌عنوان کتابخانه:
    from hush_denoise import denoise_array, denoise_file
    y = denoise_array(x_int16, sr=16000)
"""
from __future__ import annotations
import os
import numpy as np
import onnxruntime as ort

SR, FFT, HOP = 16000, 320, 160
N_FREQS, NB_ERB, NB_DF, DF_ORDER = 161, 32, 64, 5
NORM_TAU = 1.0
# libdf ERB widths (مقادیر ثابت برای این تنظیمات، از feature_extract.cc)
ERB_WIDTHS = np.array([2] * 20 + [3, 6, 7, 7, 8, 8, 10, 12, 12, 14, 16, 18], dtype=np.int64)
assert ERB_WIDTHS.sum() == N_FREQS
WNORM = 1.0 / (FFT * FFT / (2.0 * HOP))          # = 1/320
ALPHA = float(np.exp(-HOP / SR / NORM_TAU))      # ≈ 0.990050

_ONNX_DIR = os.environ.get('HUSH_ONNX_DIR', '/home/user/.cache/hush/onnx')
_WIN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'hush_libdf_window.npy')
_sessions: dict | None = None
_window: np.ndarray | None = None


def _win() -> np.ndarray:
    global _window
    if _window is None:
        _window = np.load(_WIN_PATH).astype(np.float32)
    return _window


def _load() -> dict:
    global _sessions
    if _sessions is None:
        so = ort.SessionOptions()
        so.intra_op_num_threads = 1
        so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        _sessions = {
            k: ort.InferenceSession(f'{_ONNX_DIR}/{k}.onnx', so, providers=['CPUExecutionProvider'])
            for k in ('enc', 'erb_dec', 'df_dec')
        }
    return _sessions


def _mean_norm(x: np.ndarray, init: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """نرمال‌سازی میانگین متحرک: state = x*(1-a) + state*a ; out = (x-state)/40"""
    out = np.empty_like(x)
    st = init.astype(np.float64).copy()
    for t in range(x.shape[0]):
        v = x[t].astype(np.float64)
        st = v * (1.0 - alpha) + st * alpha
        out[t] = (v - st) / 40.0
    return out


def _unit_norm(spec: np.ndarray, init: np.ndarray, alpha: float = ALPHA) -> np.ndarray:
    """نرمال‌سازی واحد (libdf band_unit_norm): spec /= sqrt(state)"""
    out = np.empty_like(spec)
    st = init.astype(np.float64).copy()
    for t in range(spec.shape[0]):
        mag = np.abs(spec[t]).astype(np.float64)
        st = mag * (1.0 - alpha) + st * alpha
        out[t] = spec[t] / np.sqrt(np.maximum(st, 1e-14))
    return out


def denoise_array(x_i16: np.ndarray, sr: int = SR, df_mode: str = 'sub_lag') -> np.ndarray:
    """ورودی: int16 مونو ۱۶kHz — خروجی: int16 نویزگیری‌شده (همان طول)

    df_mode (نحوهٔ اعمال فیلتر DeepFilter):
      'conv'    : y = Σ c_o · x[t+o-4]        (پورت C++ همان‌طور که نوشته شده)
      'sub'     : y = x[t] − Σ c_o · x[t+o-4]
      'sub_lag' : y = x[t] − Σ c_{o-1} · x[t−o]   ← روش مرجع libdf/DF3
      'conv_lag': y = Σ c_{o-1} · x[t−o]
    """
    assert sr == SR, 'Hush فقط 16kHz'
    s = _load()
    x = x_i16.astype(np.float32) / 32768.0
    n = x.size

    # --- ۱) پدینگ مطابق libdf: reflect 160 در ابتدا + ۳۲۰ صفر در انتها
    padded = np.zeros(HOP + n + FFT, dtype=np.float32)
    padded[HOP:HOP + n] = x
    padded[:HOP] = x[HOP - 1::-1] if n >= HOP else np.pad(x, (HOP - n, 0))[::-1]

    # --- ۲) STFT (center=false، پنجرهٔ libdf)
    w = _win()
    T = 1 + (padded.size - FFT) // HOP
    idx = np.arange(FFT)[None, :] + HOP * np.arange(T)[:, None]
    frames = padded[idx] * w[None, :]
    spec = np.fft.rfft(frames, n=FFT, axis=1)                  # (T,161) complex

    # --- ۳) ویژگی‌ها
    specn = spec * WNORM
    power = (np.abs(specn) ** 2)
    offs = np.concatenate([[0], np.cumsum(ERB_WIDTHS)])
    erb_pow = np.stack([power[:, offs[e]:offs[e + 1]].mean(axis=1) for e in range(NB_ERB)], axis=1)
    erb_db = 10.0 * np.log10(np.maximum(erb_pow, 1e-10))
    feat_erb = _mean_norm(erb_db, np.linspace(-60.0, -90.0, NB_ERB))

    spec_unitspec = specn[:, :NB_DF]
    df_un = _unit_norm(spec_unitspec, np.linspace(0.001, 0.0001, NB_DF))
    feat_spec = np.stack([df_un.real, df_un.imag], axis=0).astype(np.float32)  # (2,T,64)

    # --- ۴) استنتاج ONNX
    erb_in = feat_erb.astype(np.float32)[None, None]           # [1,1,T,32]
    spec_in = feat_spec[None]                                  # [1,2,T,64]
    out = s['enc'].run(['e0', 'e1', 'e2', 'e3', 'emb', 'c0', 'lsnr'],
                       {'feat_erb': erb_in, 'feat_spec': spec_in})
    e0, e1, e2, e3, emb, c0 = out[0], out[1], out[2], out[3], out[4], out[5]
    m = s['erb_dec'].run(['m'], {'emb': emb, 'e3': e3, 'e2': e2, 'e1': e1, 'e0': e0})[0]
    coefs = s['df_dec'].run(['coefs'], {'emb': emb, 'c0': c0})[0]   # [1,T,64,10]

    # --- ۵) ماسک ERB → کل ۱۶۱ بین
    m2 = m.reshape(T, NB_ERB)
    fb_inv = np.zeros((NB_ERB, N_FREQS), dtype=np.float32)
    b = 0
    for e in range(NB_ERB):
        fb_inv[e, b:b + ERB_WIDTHS[e]] = 1.0 / ERB_WIDTHS[e]
        b += ERB_WIDTHS[e]
    mask_full = m2 @ fb_inv                                      # (T,161)

    # --- ۶) فیلتر DF روی ۶۴ بین اول
    c = coefs.reshape(T, NB_DF, DF_ORDER, 2)                     # last dim = re/im
    sp = spec[:, :NB_DF]
    if df_mode in ('conv', 'sub'):
        sp_pad = np.concatenate([np.zeros((DF_ORDER - 1, NB_DF), np.complex64), sp.astype(np.complex64)], axis=0)
        taps = [(o, o) for o in range(DF_ORDER)]
    else:  # *_lag : تأخیر ۱..۵ فریم
        sp_pad = np.concatenate([np.zeros((DF_ORDER, NB_DF), np.complex64), sp.astype(np.complex64)], axis=0)
        taps = [(o - 1, o) for o in range(1, DF_ORDER + 1)]
    re_s = sp_pad.real
    im_s = sp_pad.imag
    acc_re = np.zeros((T, NB_DF), np.float64)
    acc_im = np.zeros((T, NB_DF), np.float64)
    for ci_o, sh in taps:
        cr = c[:, :, ci_o, 0].astype(np.float64)
        ci = c[:, :, ci_o, 1].astype(np.float64)
        pr = re_s[sh:sh + T]
        pi = im_s[sh:sh + T]
        acc_re += pr * cr - pi * ci
        acc_im += pi * cr + pr * ci
    if df_mode.startswith('sub'):
        acc_re = sp.real.astype(np.float64) - acc_re
        acc_im = sp.imag.astype(np.float64) - acc_im
    spec_out = np.empty((T, N_FREQS), np.complex64)
    spec_out[:, :NB_DF] = acc_re + 1j * acc_im
    spec_out[:, NB_DF:] = spec[:, NB_DF:] * mask_full[:, NB_DF:]

    # --- ۷) ISTFT (بازسازی با جمع مربع پنجره = ۱ در ناحیهٔ مصرفی)
    fr = np.fft.irfft(spec_out, n=FFT, axis=1) * w[None, :]
    out_len = padded.size
    y = np.zeros(out_len, np.float64)
    wsum = np.zeros(out_len, np.float64)
    for t in range(T):
        a = t * HOP
        y[a:a + FFT] += fr[t]
        wsum[a:a + FFT] += w.astype(np.float64) ** 2
    nz = wsum > 1e-8
    y[nz] /= wsum[nz]
    enh = y[HOP:HOP + n]                                         # حذف تأخیر
    return np.clip(enh * 32768.0, -32768, 32767).astype(np.int16)


def denoise_file(src: str, dst: str) -> None:
    """فایل WAV مونو ۱۶kHz int16 → فایل WAV نویزگیری‌شده"""
    import soundfile as sf
    x, sr = sf.read(src, dtype='int16')
    if x.ndim > 1:
        x = x[:, 0]
    sf.write(dst, denoise_array(x, sr), sr, subtype='PCM_16')


if __name__ == '__main__':
    import sys, time
    t0 = time.time()
    denoise_file(sys.argv[1], sys.argv[2])
    print(f'✓ {sys.argv[1]} → {sys.argv[2]}  [{time.time()-t0:.1f}s]')
